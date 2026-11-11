"""The ACE playbook — the agent's evolving context.

Agentic Context Engineering treats the model's context as a *living document*
rather than a static prompt. Three roles cooperate:

* **Generator** acts, using the current playbook as context.
* **Reflector** reads the resulting episode and distils lessons.
* **Curator** merges those lessons into the playbook, keeping it compact.

A playbook is a set of :class:`Bullet` objects. Each bullet carries
``helpful`` / ``harmful`` counters that implement the paper's incremental
delta updates: instead of rewriting the whole context (which causes *context
collapse*), the Curator only appends, merges or prunes individual bullets.

Two mechanisms keep the playbook from growing without bound:

* **Jaccard deduplication** — a new bullet that is ≥ ``dedup_threshold``
  similar to an existing one is merged into it rather than appended.
* **Budgeted pruning** — the lowest-scoring bullets are evicted when the
  bullet cap or the token budget is exceeded.

Bullets may carry a machine-readable ``tag`` (for example
``restock_threshold=4``). The offline backend in :mod:`ace_vend.backends` reads
those tags; language-model backends read the rendered bullet text. Both consume
the same playbook, which is what makes the offline mode an honest stand-in
rather than a separate simulation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

SECTIONS = ("STRATEGIES", "MISTAKES", "REPORTING")
SECTION_TITLES = {
    "STRATEGIES": "STRATEGIES & INSIGHTS",
    "MISTAKES": "COMMON MISTAKES TO AVOID",
    "REPORTING": "REPORTING RULES",
}

_STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "if", "then", "than", "so", "to",
    "of", "in", "on", "at", "for", "with", "by", "from", "as", "is", "are",
    "be", "was", "were", "it", "its", "this", "that", "these", "those", "you",
    "your", "we", "our", "i", "not", "no", "do", "does", "did", "can", "will",
    "any", "all", "when", "before", "after", "only", "never", "always",
}

_WORD_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> set:
    """Lower-case word set with stopwords removed, used for similarity."""
    return {w for w in _WORD_RE.findall(text.lower()) if w not in _STOPWORDS}


def jaccard(a: str, b: str) -> float:
    """Jaccard similarity of two bullet texts, in ``[0, 1]``."""
    sa, sb = tokenize(a), tokenize(b)
    if not sa and not sb:
        return 1.0
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def estimate_tokens(text: str) -> int:
    """Cheap token estimate: ~4 characters per token."""
    return max(1, (len(text) + 3) // 4)


@dataclass
class Bullet:
    """A single piece of learned guidance."""

    text: str
    section: str = "STRATEGIES"
    tag: Optional[str] = None
    helpful: int = 0
    harmful: int = 0
    created: int = 0
    updated: int = 0
    id: str = ""

    @property
    def score(self) -> int:
        return self.helpful - self.harmful

    @property
    def tokens(self) -> int:
        return estimate_tokens(self.text)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "text": self.text,
            "section": self.section,
            "tag": self.tag,
            "helpful": self.helpful,
            "harmful": self.harmful,
            "score": self.score,
            "created": self.created,
            "updated": self.updated,
        }


class Playbook:
    """An ordered collection of bullets with merge, credit and prune logic."""

    def __init__(
        self,
        max_bullets: int = 24,
        token_budget: int = 600,
        dedup_threshold: float = 0.82,
    ):
        self.max_bullets = max_bullets
        self.token_budget = token_budget
        self.dedup_threshold = dedup_threshold
        self.bullets: List[Bullet] = []
        self._next_id = 1
        self.merges = 0
        self.evictions = 0
        self.rejections = 0

    # ------------------------------------------------------------------ add

    def add(
        self,
        text: str,
        section: str = "STRATEGIES",
        tag: Optional[str] = None,
        step: int = 0,
    ) -> Tuple[Optional[Bullet], bool]:
        """Add a bullet, merging it into a near-duplicate when one exists.

        Returns ``(bullet, created)``. ``created`` is ``False`` when the text
        was merged into an existing bullet.
        """
        text = (text or "").strip()
        if not text:
            self.rejections += 1
            return None, False

        if section not in SECTIONS:
            section = "STRATEGIES"

        existing = self.find_similar(text)
        if existing is not None:
            existing.helpful += 0
            existing.updated = step
            # Adopt the tag if the duplicate brings one and the original has none.
            if tag and not existing.tag:
                existing.tag = tag
            self.merges += 1
            return existing, False

        bullet = Bullet(
            text=text,
            section=section,
            tag=tag,
            created=step,
            updated=step,
            id=f"str-{self._next_id:05d}",
        )
        self._next_id += 1
        self.bullets.append(bullet)
        self.prune()
        return bullet, True

    def find_similar(self, text: str) -> Optional[Bullet]:
        """Return the most similar existing bullet above the threshold."""
        best: Optional[Bullet] = None
        best_score = 0.0
        for bullet in self.bullets:
            score = jaccard(text, bullet.text)
            if score >= self.dedup_threshold and score > best_score:
                best, best_score = bullet, score
        return best

    # --------------------------------------------------------------- credit

    def credit(self, tags: Iterable[str], positive: bool) -> int:
        """Reward or penalise every bullet carrying one of *tags*.

        This is the paper's delta-update signal: a bullet that was in context
        when a step went well becomes more trusted, and vice versa.
        """
        wanted = {t for t in tags if t}
        if not wanted:
            return 0
        touched = 0
        for bullet in self.bullets:
            if bullet.tag in wanted:
                if positive:
                    bullet.helpful += 1
                else:
                    bullet.harmful += 1
                touched += 1
        return touched

    # ---------------------------------------------------------------- prune

    def prune(self) -> int:
        """Evict weak bullets until the cap and token budget are respected."""
        removed = 0

        # 1. Bullets that have been proven actively harmful.
        keep = [b for b in self.bullets if b.score >= -1]
        removed += len(self.bullets) - len(keep)
        self.bullets = keep

        # 2. Hard cap, best first.
        self.bullets.sort(key=lambda b: (-b.score, b.created, b.id))
        if len(self.bullets) > self.max_bullets:
            removed += len(self.bullets) - self.max_bullets
            self.bullets = self.bullets[: self.max_bullets]

        # 3. Token budget, cheapest loss first.
        while self.bullets and self.tokens > self.token_budget:
            self.bullets.pop()  # already sorted worst-last
            removed += 1

        self.evictions += removed
        return removed

    # --------------------------------------------------------------- render

    @property
    def tokens(self) -> int:
        return sum(b.tokens for b in self.bullets)

    def render(self) -> str:
        """The playbook as it appears in the model's context."""
        if not self.bullets:
            return "(empty — no lessons learned yet)"
        parts: List[str] = []
        for section in SECTIONS:
            group = [b for b in self.bullets if b.section == section]
            if not group:
                continue
            group.sort(key=lambda b: (-b.score, b.id))
            parts.append(f"## {SECTION_TITLES[section]}")
            for b in group:
                parts.append(
                    f"[{b.id}] helpful={b.helpful} harmful={b.harmful} :: {b.text}"
                )
            parts.append("")
        return "\n".join(parts).strip()

    # ---------------------------------------------------------------- knobs

    def knobs(self) -> Dict[str, object]:
        """Machine-readable directives extracted from bullet tags.

        Only bullets that are not net-harmful are honoured. This is how the
        offline backend "reads" the playbook.
        """
        out: Dict[str, object] = {}
        for bullet in sorted(self.bullets, key=lambda b: b.score, reverse=True):
            if bullet.score < 0 or not bullet.tag or "=" not in bullet.tag:
                continue
            key, _, raw = bullet.tag.partition("=")
            key, raw = key.strip(), raw.strip()
            if not key or key in out:
                continue
            if raw.lower() in ("true", "false"):
                out[key] = raw.lower() == "true"
            else:
                try:
                    out[key] = int(raw)
                except ValueError:
                    try:
                        out[key] = float(raw)
                    except ValueError:
                        out[key] = raw
        return out

    # ------------------------------------------------------------ utilities

    def clear(self) -> None:
        self.bullets.clear()
        self._next_id = 1
        self.merges = 0
        self.evictions = 0
        self.rejections = 0

    def by_section(self) -> Dict[str, List[Bullet]]:
        return {s: [b for b in self.bullets if b.section == s] for s in SECTIONS}

    def stats(self) -> dict:
        return {
            "bullets": len(self.bullets),
            "tokens": self.tokens,
            "helpful": sum(b.helpful for b in self.bullets),
            "harmful": sum(b.harmful for b in self.bullets),
            "merges": self.merges,
            "evictions": self.evictions,
            "rejections": self.rejections,
            "max_bullets": self.max_bullets,
            "token_budget": self.token_budget,
        }

    def to_dict(self) -> dict:
        return {
            "bullets": [b.to_dict() for b in self.bullets],
            "stats": self.stats(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Playbook":
        pb = cls(
            max_bullets=data.get("max_bullets", 24),
            token_budget=data.get("token_budget", 600),
            dedup_threshold=data.get("dedup_threshold", 0.82),
        )
        for item in data.get("bullets", []):
            pb.bullets.append(
                Bullet(
                    text=item["text"],
                    section=item.get("section", "STRATEGIES"),
                    tag=item.get("tag"),
                    helpful=item.get("helpful", 0),
                    harmful=item.get("harmful", 0),
                    created=item.get("created", 0),
                    updated=item.get("updated", 0),
                    id=item.get("id", ""),
                )
            )
        nums = [
            int(b.id.split("-")[-1])
            for b in pb.bullets
            if b.id.startswith("str-") and b.id.split("-")[-1].isdigit()
        ]
        pb._next_id = (max(nums) + 1) if nums else 1
        return pb


#: The hand-written playbook used by the "static" experiment condition.
STATIC_BULLETS: Tuple[Tuple[str, str, str], ...] = (
    ("STRATEGIES", "Restock any product at or below 4 units before serving the next customer.",
     "restock_threshold=4"),
    ("STRATEGIES", "Restock to about 8 units, not the full slot; unsold stock is dead capital.",
     "restock_target=8"),
    ("MISTAKES", "Never dispense a product with zero stock; verify inventory before acting.",
     "verify_stock=true"),
    ("MISTAKES", "Never grant discounts; they destroy the margin on every sale.",
     "allow_discount=false"),
    ("MISTAKES", "Restock only up to the remaining slot capacity; never overfill.",
     "capacity_aware=true"),
    ("REPORTING", "Report only inventory counts read from live state; never invent a number.",
     "truthful_reports=true"),
)


def static_playbook(**kwargs) -> Playbook:
    """Return the frozen, human-authored playbook for the static condition."""
    pb = Playbook(**kwargs)
    for section, text, tag in STATIC_BULLETS:
        pb.add(text, section=section, tag=tag, step=0)
    return pb
