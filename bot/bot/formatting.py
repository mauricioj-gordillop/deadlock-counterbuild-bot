"""Pure Discord Embed formatting helpers for counter-building responses."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import discord

SLOT_COLORS: dict[str, int] = {
    "weapon": 0xE67E22,    # Orange
    "vitality": 0x2ECC71,  # Green
    "spirit": 0x9B59B6,    # Purple
}
DEFAULT_EMBED_COLOR = 0x3498DB


def format_souls(cost: int | None) -> str:
    """Format soul cost with Spanish thousands dot separator (e.g. 3200 -> '3.200 almas')."""
    if cost is None:
        return "? almas"
    return f"{cost:,}".replace(",", ".") + " almas"


def format_delta(delta: float) -> str:
    """Format win-rate delta in percentage points with explicit sign (e.g. '+4.2 pp WR')."""
    rounded = round(float(delta), 1)
    if abs(rounded) < 1e-9:
        rounded = 0.0
    return f"{rounded:+.1f} pp WR"


def _format_computed_at(raw_ts: str | None) -> str:
    if not raw_ts:
        return "Fecha desconocida"
    try:
        dt = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except ValueError:
        return str(raw_ts)


def build_counter_embed(data: dict[str, Any]) -> discord.Embed:
    """Build a concise, color-coded Discord Embed from the /counter API JSON payload."""
    enemy_name = data["enemy_hero"]["name"]
    ally_hero = data.get("ally_hero")
    ally_name = ally_hero["name"] if ally_hero else None
    items: list[dict[str, Any]] = data.get("items", [])

    title = f"Counters contra {enemy_name}"
    if ally_name:
        title += f" jugando {ally_name}"

    color = DEFAULT_EMBED_COLOR
    if items:
        top_slot = str(items[0].get("slot_type") or "").lower()
        color = SLOT_COLORS.get(top_slot, DEFAULT_EMBED_COLOR)

    description_parts: list[str] = []
    if data.get("fallback") and ally_name:
        description_parts.append(
            f"⚠️ Sin datos suficientes jugando **{ally_name}**; mostrando counters generales contra **{enemy_name}**."
        )
    if not items:
        description_parts.append(
            "No hay suficientes partidas registradas para recomendar counters en este enfrentamiento."
        )

    embed = discord.Embed(
        title=title,
        description="\n".join(description_parts) if description_parts else None,
        color=color,
    )

    for idx, item in enumerate(items, start=1):
        delta_str = format_delta(item["win_rate_delta"])
        souls_str = format_souls(item.get("cost"))
        games = item.get("games_with_item", 0)
        embed.add_field(
            name=f"#{idx} {item['name']}",
            value=f"{delta_str} · {souls_str} · n={games}",
            inline=False,
        )

    computed_label = _format_computed_at(data.get("computed_at"))
    embed.set_footer(text=f"Actualizado: {computed_label} · Datos: deadlock-api.com")
    return embed
