"""In-memory RAM store for sub-millisecond counter-building lookups."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

from bot.names import HeroRecord, normalize_hero_name, resolve_hero_query


class HeroNotFoundError(Exception):
    """Raised when an enemy or allied hero query cannot be resolved."""

    def __init__(self, message: str, suggestions: list[str] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.suggestions = suggestions or []


class StoreUnavailableError(Exception):
    """Raised when the in-memory Gold snapshot has not been loaded yet."""


@dataclass(frozen=True)
class ItemRecord:
    item_id: int
    name: str
    cost: int | None
    tier: int | None
    slot_type: str | None


@dataclass(frozen=True)
class CounterRuleRecord:
    ally_hero_id: int
    enemy_hero_id: int
    item_id: int
    win_rate_delta: float
    win_rate_with_item: float | None
    games_with_item: int
    rank: int
    computed_at: datetime | None


@dataclass(frozen=True)
class CounterSnapshot:
    """Immutable snapshot of Databricks Gold + Silver dimensions kept in RAM."""

    heroes: tuple[HeroRecord, ...]
    items_by_id: dict[int, ItemRecord]
    counters_by_pair: dict[tuple[int, int], tuple[CounterRuleRecord, ...]]
    total_rules: int
    source: str
    loaded_at: datetime


def build_snapshot(
    *,
    heroes: Iterable[HeroRecord],
    items: Iterable[ItemRecord],
    counters: Iterable[CounterRuleRecord],
    source: str,
) -> CounterSnapshot:
    """Index heroes, items, and ranked counter rules into an immutable RAM snapshot."""
    dedup_heroes: dict[int, HeroRecord] = {}
    for h in heroes:
        norm = h.name_normalized or normalize_hero_name(h.name)
        dedup_heroes[h.hero_id] = HeroRecord(
            hero_id=h.hero_id, name=h.name.strip(), name_normalized=norm
        )
    sorted_heroes = tuple(sorted(dedup_heroes.values(), key=lambda x: x.name.lower()))

    items_by_id = {it.item_id: it for it in items}

    grouped: dict[tuple[int, int], list[CounterRuleRecord]] = defaultdict(list)
    total = 0
    for rule in counters:
        if rule.item_id not in items_by_id:
            continue
        grouped[(rule.enemy_hero_id, rule.ally_hero_id)].append(rule)
        total += 1

    counters_by_pair: dict[tuple[int, int], tuple[CounterRuleRecord, ...]] = {
        pair: tuple(sorted(rules, key=lambda r: (r.rank, -r.win_rate_delta, r.item_id)))
        for pair, rules in grouped.items()
    }

    return CounterSnapshot(
        heroes=sorted_heroes,
        items_by_id=items_by_id,
        counters_by_pair=counters_by_pair,
        total_rules=total,
        source=source,
        loaded_at=datetime.now(timezone.utc),
    )


class CounterStore:
    """Thread-safe/atomic holder of the active CounterSnapshot."""

    def __init__(self, snapshot: CounterSnapshot | None = None) -> None:
        self._snapshot = snapshot

    @property
    def is_ready(self) -> bool:
        return self._snapshot is not None

    def update_snapshot(self, snapshot: CounterSnapshot) -> None:
        """Atomically swap the active in-memory snapshot."""
        self._snapshot = snapshot

    def list_heroes(self) -> list[HeroRecord]:
        snap = self._snapshot
        return list(snap.heroes) if snap is not None else []

    def health_summary(self) -> tuple[bool, dict[str, Any]]:
        snap = self._snapshot
        if snap is None:
            return False, {"status": "loading", "heroes": 0, "rules": 0, "source": None, "loaded_at": None}
        return True, {
            "status": "ok",
            "source": snap.source,
            "heroes": len(snap.heroes),
            "rules": snap.total_rules,
            "loaded_at": snap.loaded_at.isoformat(),
        }

    def get_counters(
        self,
        enemy_query: str,
        *,
        ally_query: str | None = None,
        limit: int = 3,
        max_limit: int = 5,
    ) -> dict[str, Any]:
        """Resolve hero names in RAM and return top counter items with ally=0 fallback."""
        snap = self._snapshot
        if snap is None:
            raise StoreUnavailableError("El catálogo de recomendaciones aún se está cargando.")

        enemy, enemy_suggestions = resolve_hero_query(enemy_query, snap.heroes)
        if enemy is None:
            raise HeroNotFoundError(
                f"Héroe enemigo no encontrado: '{enemy_query}'",
                enemy_suggestions,
            )

        ally: HeroRecord | None = None
        ally_id = 0
        if ally_query is not None and ally_query.strip():
            ally, ally_suggestions = resolve_hero_query(ally_query, snap.heroes)
            if ally is None:
                raise HeroNotFoundError(
                    f"Héroe aliado no encontrado: '{ally_query}'",
                    ally_suggestions,
                )
            ally_id = ally.hero_id

        effective_limit = max(1, min(limit, max_limit))
        rules = snap.counters_by_pair.get((enemy.hero_id, ally_id), ())
        fallback = False
        if ally is not None and not rules:
            rules = snap.counters_by_pair.get((enemy.hero_id, 0), ())
            fallback = True

        selected = rules[:effective_limit]
        computed_at = (
            selected[0].computed_at.isoformat()
            if selected and selected[0].computed_at is not None
            else None
        )

        items_out = []
        for rule in selected:
            item_meta = snap.items_by_id[rule.item_id]
            items_out.append(
                {
                    "item_id": rule.item_id,
                    "name": item_meta.name,
                    "cost": item_meta.cost,
                    "tier": item_meta.tier,
                    "slot_type": item_meta.slot_type,
                    "win_rate_delta": rule.win_rate_delta,
                    "win_rate_with_item": rule.win_rate_with_item,
                    "games_with_item": rule.games_with_item,
                }
            )

        return {
            "enemy_hero": {"id": enemy.hero_id, "name": enemy.name},
            "ally_hero": {"id": ally.hero_id, "name": ally.name} if ally is not None else None,
            "fallback": fallback,
            "computed_at": computed_at,
            "items": items_out,
        }
