"""Tests for the ACE playbook: merging, crediting, pruning and knobs."""

from __future__ import annotations

import pytest

from ace_vend.playbook import (
    STATIC_BULLETS,
    Playbook,
    jaccard,
    static_playbook,
    tokenize,
)


class TestSimilarity:
    def test_identical_texts_are_maximally_similar(self):
        assert jaccard("restock before serving", "restock before serving") == 1.0

    def test_unrelated_texts_are_dissimilar(self):
        assert jaccard("restock the machine", "discount the coffee") < 0.3

    def test_stopwords_are_ignored(self):
        assert tokenize("the and of") == set()
        assert "never" not in tokenize("never grant discounts")


class TestAddAndDedup:
    def test_add_assigns_sequential_ids(self):
        pb = Playbook()
        first, created_a = pb.add("Never grant discounts.")
        second, created_b = pb.add("Restock when a slot is empty.")

        assert created_a and created_b
        assert first.id == "str-00001"
        assert second.id == "str-00002"
        assert len(pb.bullets) == 2

    def test_near_duplicate_is_merged_not_appended(self):
        pb = Playbook()
        pb.add("Never grant discounts; they destroy the margin.")
        pb.add("Never grant discounts, they destroy the margin.")

        assert len(pb.bullets) == 1
        assert pb.merges == 1

    def test_duplicate_can_donate_its_tag(self):
        pb = Playbook()
        pb.add("Restock when stock is low.")
        pb.add("Restock when stock is low!", tag="restock_threshold=4")

        assert len(pb.bullets) == 1
        assert pb.bullets[0].tag == "restock_threshold=4"

    def test_empty_text_is_rejected(self):
        pb = Playbook()
        bullet, created = pb.add("   ")
        assert bullet is None
        assert not created
        assert pb.rejections == 1

    def test_unknown_section_falls_back_to_strategies(self):
        pb = Playbook()
        bullet, _ = pb.add("Something true.", section="NONSENSE")
        assert bullet.section == "STRATEGIES"


class TestCredit:
    def test_credit_marks_helpful(self):
        pb = Playbook()
        pb.add("Never grant discounts.", tag="allow_discount=false")
        assert pb.credit(["allow_discount=false"], positive=True) == 1
        assert pb.bullets[0].helpful == 1
        assert pb.bullets[0].score == 1

    def test_credit_marks_harmful(self):
        pb = Playbook()
        pb.add("Never grant discounts.", tag="allow_discount=false")
        pb.credit(["allow_discount=false"], positive=False)
        assert pb.bullets[0].harmful == 1
        assert pb.bullets[0].score == -1

    def test_credit_ignores_unknown_tags(self):
        pb = Playbook()
        pb.add("Never grant discounts.", tag="allow_discount=false")
        assert pb.credit(["nope=1"], positive=True) == 0
        assert pb.bullets[0].score == 0


class TestPruning:
    def test_net_harmful_bullets_are_evicted(self):
        pb = Playbook()
        pb.add("A bad idea.", tag="bad=1")
        pb.credit(["bad=1"], positive=False)
        pb.credit(["bad=1"], positive=False)

        removed = pb.prune()
        assert removed >= 1
        assert pb.bullets == []

    def test_bullet_cap_is_enforced(self):
        pb = Playbook(max_bullets=3)
        for i in range(6):
            pb.add(f"Distinct lesson number {i} about vending machines {i}.")
        assert len(pb.bullets) <= 3

    def test_token_budget_is_enforced(self):
        pb = Playbook(token_budget=5)
        pb.add("A very long lesson that definitely exceeds a tiny token budget.")
        assert pb.bullets == []
        assert pb.evictions >= 1

    def test_high_scoring_bullets_survive_the_cap(self):
        pb = Playbook(max_bullets=2)
        pb.add("Low value lesson about nothing much.", tag="low=1")
        pb.add("High value lesson about restocking.", tag="high=1")
        pb.credit(["high=1"], positive=True)
        pb.add("Another lesson about pricing shelves.", tag="mid=1")

        texts = [b.text for b in pb.bullets]
        assert "High value lesson about restocking." in texts


class TestKnobs:
    def test_knobs_parses_integers(self):
        pb = Playbook()
        pb.add("Restock to eight.", tag="restock_target=8")
        assert pb.knobs()["restock_target"] == 8

    def test_knobs_parses_booleans(self):
        pb = Playbook()
        pb.add("Never discount.", tag="allow_discount=false")
        pb.add("Report truthfully.", tag="truthful_reports=true")
        knobs = pb.knobs()
        assert knobs["allow_discount"] is False
        assert knobs["truthful_reports"] is True

    def test_knobs_parses_strings_and_floats(self):
        pb = Playbook()
        pb.add("Be nice.", tag="tone=friendly")
        pb.add("Mark up a bit.", tag="markup=1.25")
        knobs = pb.knobs()
        assert knobs["tone"] == "friendly"
        assert knobs["markup"] == pytest.approx(1.25)

    def test_net_harmful_bullets_are_not_honoured(self):
        pb = Playbook()
        pb.add("A bad idea.", tag="bad=1")
        pb.credit(["bad=1"], positive=False)
        pb.credit(["bad=1"], positive=False)
        assert "bad" not in pb.knobs()

    def test_first_knob_wins_when_duplicated(self):
        pb = Playbook()
        pb.add("Restock at four.", tag="restock_threshold=4")
        pb.add("Restock at nine, different words entirely.", tag="restock_threshold=9")
        assert pb.knobs()["restock_threshold"] == 4

    def test_bullets_without_tags_produce_no_knobs(self):
        pb = Playbook()
        pb.add("Serve the customer first.")
        assert pb.knobs() == {}


class TestRender:
    def test_empty_playbook_says_so(self):
        assert "empty" in Playbook().render()

    def test_render_groups_by_section(self):
        pb = Playbook()
        pb.add("Restock early.", section="STRATEGIES")
        pb.add("Never invent stock.", section="REPORTING")
        rendered = pb.render()

        assert "STRATEGIES & INSIGHTS" in rendered
        assert "REPORTING RULES" in rendered
        assert "Restock early." in rendered

    def test_render_includes_score_metadata(self):
        pb = Playbook()
        pb.add("Restock early.", tag="early=1")
        pb.credit(["early=1"], positive=True)
        rendered = pb.render()
        assert "helpful=1" in rendered
        assert "harmful=0" in rendered


class TestStaticPlaybook:
    def test_static_playbook_has_every_bullet(self):
        pb = static_playbook()
        assert len(pb.bullets) == len(STATIC_BULLETS)

    def test_static_playbook_exposes_the_expected_knobs(self):
        knobs = static_playbook().knobs()
        assert knobs["restock_threshold"] == 4
        assert knobs["restock_target"] == 8
        assert knobs["allow_discount"] is False
        assert knobs["capacity_aware"] is True
        assert knobs["truthful_reports"] is True

    def test_static_playbook_never_learns(self):
        pb = static_playbook()
        before = len(pb.bullets)
        # Simulating the ACE credit path must not add bullets.
        pb.credit(["restock_threshold=4"], positive=True)
        assert len(pb.bullets) == before


class TestSerialisation:
    def test_round_trip_preserves_bullets(self):
        pb = Playbook()
        pb.add("Restock early.", tag="early=1", section="STRATEGIES")
        pb.credit(["early=1"], positive=True)

        restored = Playbook.from_dict(pb.to_dict())

        assert len(restored.bullets) == 1
        assert restored.bullets[0].text == "Restock early."
        assert restored.bullets[0].helpful == 1

    def test_next_id_continues_after_round_trip(self):
        pb = Playbook()
        pb.add("First lesson.")
        pb.add("Second lesson, different enough words.")
        restored = Playbook.from_dict(pb.to_dict())
        bullet, _ = restored.add("Third lesson about something else entirely.")
        assert bullet.id == "str-00003"

    def test_stats_counts_bullets_and_tokens(self):
        pb = Playbook()
        pb.add("Restock early.")
        stats = pb.stats()
        assert stats["bullets"] == 1
        assert stats["tokens"] > 0
