# backend/playbook_manager.py — ACE bullet-format playbook persistence

import re
import logging
from pathlib import Path
from config import PLAYBOOK_PATH, MAX_PLAYBOOK_BULLETS, SIMILARITY_THRESHOLD

log = logging.getLogger(__name__)

SECTIONS = ["STRATEGIES & INSIGHTS", "COMMON MISTAKES TO AVOID", "REPORTING RULES"]
BULLET_RE = re.compile(
    r"\[str-(\d+)\]\s+helpful=(\d+)\s+harmful=(\d+)\s*::\s*(.+)"
)


class Bullet:
    def __init__(self, idx: int, helpful: int, harmful: int, text: str, section: str = SECTIONS[0]):
        self.idx = idx
        self.helpful = helpful
        self.harmful = harmful
        self.text = text.strip()
        self.section = section

    @property
    def score(self) -> int:
        return self.helpful - self.harmful

    def __str__(self):
        return f"[str-{self.idx:05d}] helpful={self.helpful} harmful={self.harmful} :: {self.text}"


class PlaybookManager:
    """Loads, merges, deduplicates and saves ACE playbook bullets."""

    def __init__(self):
        self.bullets: list[Bullet] = []
        self._next_idx = 1
        self._load()

    # ── Persistence ─────────────────────────────────────────────────────────

    def _load(self):
        path = Path(PLAYBOOK_PATH)
        if not path.exists():
            self._save()
            return
        current_section = SECTIONS[0]
        for line in path.read_text().splitlines():
            line = line.strip()
            for s in SECTIONS:
                if line.startswith(f"## {s}"):
                    current_section = s
                    break
            m = BULLET_RE.match(line)
            if m:
                idx, helpful, harmful, text = int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4)
                self.bullets.append(Bullet(idx, helpful, harmful, text, current_section))
                self._next_idx = max(self._next_idx, idx + 1)

    def _save(self):
        path = Path(PLAYBOOK_PATH)
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = []
        for section in SECTIONS:
            lines.append(f"## {section}")
            for b in self.bullets:
                if b.section == section:
                    lines.append(str(b))
            lines.append("")
        path.write_text("\n".join(lines))

    # ── Public API ───────────────────────────────────────────────────────────

    def render(self, token_budget: int = 4000) -> str:
        """
        Return the playbook as a prompt-ready string within budget.
        
        MODERATE 7 fix: Replaced recursion with iteration to avoid stack overflow.
        """
        lines = []
        for section in SECTIONS:
            section_bullets = [b for b in self.bullets if b.section == section]
            if section_bullets:
                lines.append(f"## {section}")
                for b in sorted(section_bullets, key=lambda x: -x.score):
                    lines.append(str(b))
                lines.append("")
        
        text = "\n".join(lines)
        
        # Rough token estimate: 1 token ≈ 4 chars
        # Use iteration instead of recursion to avoid stack overflow
        while len(text) // 4 > token_budget and self.bullets:
            # Drop lowest-score bullet
            worst = min(self.bullets, key=lambda b: b.score)
            self.bullets.remove(worst)
            
            # Recalculate text iteratively
            lines = []
            for section in SECTIONS:
                section_bullets = [b for b in self.bullets if b.section == section]
                if section_bullets:
                    lines.append(f"## {section}")
                    for b in sorted(section_bullets, key=lambda x: -x.score):
                        lines.append(str(b))
                    lines.append("")
            text = "\n".join(lines)
        
        return text

    def add_or_update(self, text: str, label: str, section: str = SECTIONS[0]) -> Bullet:
        """Add a bullet or increment helpful/harmful on an existing similar one."""
        similar = self._find_similar(text)
        if similar:
            if label == "helpful":
                similar.helpful += 1
            elif label == "harmful":
                similar.harmful += 1
            log.debug("Updated existing bullet [str-%05d]", similar.idx)
            b = similar
        else:
            b = Bullet(self._next_idx, 1 if label == "helpful" else 0,
                       1 if label == "harmful" else 0, text, section)
            self._next_idx += 1
            self.bullets.append(b)
            log.debug("Added new bullet [str-%05d]", b.idx)
        self._prune()
        self._save()
        return b

    def count(self) -> int:
        return len(self.bullets)

    def all_bullets(self) -> list[dict]:
        return [{"idx": b.idx, "helpful": b.helpful, "harmful": b.harmful,
                 "text": b.text, "section": b.section, "score": b.score}
                for b in sorted(self.bullets, key=lambda x: -x.score)]

    # ── Internals ────────────────────────────────────────────────────────────

    def _find_similar(self, text: str) -> Bullet | None:
        words_new = set(text.lower().split())
        for b in self.bullets:
            words_old = set(b.text.lower().split())
            if not words_new or not words_old:
                continue
            overlap = len(words_new & words_old) / len(words_new | words_old)
            if overlap >= SIMILARITY_THRESHOLD:
                return b
        return None

    def _prune(self):
        if len(self.bullets) > MAX_PLAYBOOK_BULLETS:
            self.bullets.sort(key=lambda b: b.score)
            removed = self.bullets.pop(0)
            log.debug("Pruned bullet [str-%05d] (score %d)", removed.idx, removed.score)
