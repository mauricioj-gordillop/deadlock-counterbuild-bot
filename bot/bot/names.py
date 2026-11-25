"""Hero name normalization, aliases, and fuzzy suggestion helpers."""

from __future__ import annotations

import difflib
import re
import unicodedata
from dataclasses import dataclass
from typing import Sequence

HERO_ALIASES: dict[str, str] = {
    "geist": "ladygeist",
    "talon": "greytalon",
    "mo": "mokrill",
    "mnk": "mokrill",
    "moandkrill": "mokrill",
    "mc": "mcginnis",
    "vin": "vindicta",
    "dyna": "dynamo",
}


@dataclass(frozen=True)
class HeroRecord:
    hero_id: int
    name: str
    name_normalized: str


def normalize_hero_name(raw: str) -> str:
    """Normalize hero input to lowercase ASCII alphanumeric string."""
    decomposed = unicodedata.normalize("NFKD", raw)
    ascii_only = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]", "", ascii_only.lower())


def resolve_hero_query(
    query: str,
    heroes: Sequence[HeroRecord],
    *,
    max_suggestions: int = 3,
) -> tuple[HeroRecord | None, list[str]]:
    """Resolve a numeric ID, alias, or hero name; return fuzzy suggestions on miss."""
    cleaned = query.strip()
    if not cleaned:
        return None, [h.name for h in heroes[:max_suggestions]]

    if cleaned.isdigit():
        hero_id = int(cleaned)
        for hero in heroes:
            if hero.hero_id == hero_id:
                return hero, []
        return None, [h.name for h in heroes[:max_suggestions]]

    normalized = normalize_hero_name(cleaned)
    canonical = HERO_ALIASES.get(normalized, normalized)

    by_norm: dict[str, HeroRecord] = {}
    for hero in heroes:
        key = hero.name_normalized or normalize_hero_name(hero.name)
        by_norm[key] = hero

    if canonical in by_norm:
        return by_norm[canonical], []

    prefix_matches = [hero for key, hero in by_norm.items() if key.startswith(canonical)]
    if len(prefix_matches) == 1:
        return prefix_matches[0], []

    close_keys = difflib.get_close_matches(
        canonical, list(by_norm.keys()), n=max_suggestions, cutoff=0.45
    )
    suggestions = [by_norm[k].name for k in close_keys]
    if not suggestions:
        suggestions = [h.name for h in prefix_matches[:max_suggestions]]
    return None, suggestions
