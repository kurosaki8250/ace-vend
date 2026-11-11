"""The three ACE roles, made explicit.

The paper describes Generator → Reflector → Curator. Keeping them as separate
objects (rather than one long method) makes each one independently testable and
makes the data flow obvious:

    request ──► Generator ──► candidate action
                    ▲                │
                    │                ▼
              playbook ◄── Curator ◄── Reflector ◄── episode
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from ace_vend.backends import Backend, BulletCandidate, Episode
from ace_vend.environment import Decision, Request, VendingEnvironment
from ace_vend.playbook import Bullet, Playbook


class Generator:
    """Produces one candidate action, conditioned on the playbook."""

    def __init__(self, backend: Backend):
        self.backend = backend

    def act(
        self,
        env: VendingEnvironment,
        request: Request,
        playbook: Playbook,
    ) -> Decision:
        return self.backend.decide(env, request, playbook)


class Reflector:
    """Turns an episode into zero or more candidate lessons."""

    def __init__(self, backend: Backend, rounds: int = 1):
        self.backend = backend
        self.rounds = max(1, rounds)

    def reflect(
        self,
        episode: Episode,
        env: VendingEnvironment,
        playbook: Playbook,
    ) -> List[BulletCandidate]:
        candidates: List[BulletCandidate] = []
        for _ in range(self.rounds):
            candidates.extend(self.backend.reflect(episode, env, playbook))
        return candidates


class Curator:
    """Merges lessons into the playbook and keeps it within budget."""

    def __init__(self, playbook: Playbook, every: int = 1):
        self.playbook = playbook
        self.every = max(1, every)
        self.last_curated = 0

    def should_curate(self, step: int) -> bool:
        return step - self.last_curated >= self.every

    def curate(
        self,
        candidates: List[BulletCandidate],
        step: int,
    ) -> Tuple[List[Bullet], int]:
        """Apply candidates. Returns ``(touched_bullets, evicted_count)``."""
        touched: List[Bullet] = []
        for candidate in candidates:
            section = "MISTAKES" if candidate.harmful else candidate.section
            bullet, _created = self.playbook.add(
                candidate.text,
                section=section,
                tag=candidate.tag,
                step=step,
            )
            if bullet is not None and bullet not in touched:
                touched.append(bullet)

        evicted = self.playbook.prune()
        self.last_curated = step
        return touched, evicted

    def credit(self, used_tags: List[str], positive: bool) -> int:
        """Delta-update the bullets that influenced a decision."""
        return self.playbook.credit(used_tags, positive)

    def reset(self) -> None:
        self.playbook.clear()
        self.last_curated = 0


def build_roles(backend: Backend, playbook: Playbook, settings) -> Tuple[Generator, Reflector, Curator]:
    """Convenience constructor wiring the roles together."""
    return (
        Generator(backend),
        Reflector(backend, rounds=getattr(settings, "reflector_rounds", 1)),
        Curator(playbook, every=getattr(settings, "curator_every", 1)),
    )
