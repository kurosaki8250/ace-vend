"""Tests for the three-condition experiment.

The key property is fairness: every condition must face the exact same customer
stream, so differences in profit come from context, not from luck.
"""

from __future__ import annotations

import json

import pytest

from ace_vend.config import Settings
from ace_vend.experiment import (
    CONDITIONS,
    as_markdown,
    as_table,
    run_condition,
    run_experiment,
)


@pytest.fixture(scope="module")
def results():
    return run_experiment(steps=60, seed=42, settings=Settings(seed=42, steps=60), save=False)


class TestFairness:
    def test_three_conditions_exist(self):
        assert [key for key, _ in CONDITIONS] == ["baseline", "static", "ace"]

    def test_every_condition_sees_the_same_requests(self, results):
        assert len({r.requests for r in results}) == 1

    def test_every_condition_runs_the_same_number_of_steps(self, results):
        assert {r.steps for r in results} == {60}
        assert all(len(r.series) == 60 for r in results)

    def test_results_are_reproducible(self):
        first = run_condition("ace", steps=20, seed=42, settings=Settings(seed=42))
        second = run_condition("ace", steps=20, seed=42, settings=Settings(seed=42))
        assert first.profit == second.profit
        assert first.stockouts == second.stockouts


class TestOutcomes:
    def test_learning_beats_no_context(self, results):
        by_key = {r.key: r for r in results}
        assert by_key["ace"].profit > by_key["baseline"].profit

    def test_handwritten_playbook_beats_no_context(self, results):
        by_key = {r.key: r for r in results}
        assert by_key["static"].profit > by_key["baseline"].profit

    def test_ace_serves_more_customers_than_baseline(self, results):
        by_key = {r.key: r for r in results}
        assert by_key["ace"].fulfilled >= by_key["baseline"].fulfilled

    def test_baseline_stockouts_exceed_the_learned_policy(self, results):
        by_key = {r.key: r for r in results}
        assert by_key["baseline"].stockouts > by_key["ace"].stockouts

    def test_baseline_has_more_guard_blocks_than_static(self, results):
        by_key = {r.key: r for r in results}
        assert by_key["baseline"].guard_blocked > by_key["static"].guard_blocked

    def test_only_ace_has_learned_bullets(self, results):
        by_key = {r.key: r for r in results}
        assert by_key["ace"].bullets > 0
        assert by_key["baseline"].bullets == 0
        assert by_key["static"].bullets == 6

    def test_ace_learns_fewer_bullets_than_the_handwritten_playbook(self, results):
        by_key = {r.key: r for r in results}
        assert by_key["ace"].bullets <= by_key["static"].bullets

    def test_every_condition_accounts_for_its_cash(self, results):
        for result in results:
            assert result.profit == pytest.approx(
                round(result.revenue - result.spend + result.salvage, 2)
            )

    def test_liquidation_zeroes_end_stock(self, results):
        for result in results:
            assert result.series[-1]["stock"] >= 0


class TestRendering:
    def test_table_lists_all_conditions(self, results):
        table = as_table(results)
        for result in results:
            assert result.label in table

    def test_markdown_is_a_valid_table(self, results):
        markdown = as_markdown(results, steps=60, seed=42)
        assert "| Condition |" in markdown
        assert "Steps: 60" in markdown
        for result in results:
            assert result.label in markdown

    def test_markdown_reports_guard_categories(self, results):
        markdown = as_markdown(results, steps=60, seed=42)
        assert "Hallucinations blocked" in markdown


class TestPersistence:
    def test_save_writes_json(self, results, tmp_path, monkeypatch):
        import ace_vend.experiment as experiment

        monkeypatch.setattr(experiment, "ensure_data_dir", lambda: tmp_path)
        experiment._save(results, steps=60, seed=42)

        path = tmp_path / "experiment_results.json"
        assert path.is_file()

        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["steps"] == 60
        assert payload["seed"] == 42
        assert len(payload["conditions"]) == 3
        assert payload["conditions"][0]["key"] == "baseline"
