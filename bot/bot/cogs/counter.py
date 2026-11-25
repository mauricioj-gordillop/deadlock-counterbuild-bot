"""Slash command /counter cog backed directly by the in-memory CounterStore."""

from __future__ import annotations

import logging
import time

import discord
from discord import app_commands
from discord.ext import commands

from bot.formatting import build_counter_embed
from bot.store import CounterStore, HeroNotFoundError, StoreUnavailableError

logger = logging.getLogger(__name__)


class CounterCog(commands.Cog):
    """Provides the strict /counter slash command served directly from RAM."""

    def __init__(
        self,
        bot: commands.Bot,
        store: CounterStore,
        *,
        default_limit: int = 3,
        max_limit: int = 5,
    ) -> None:
        self.bot = bot
        self.store = store
        self.default_limit = default_limit
        self.max_limit = max_limit

    async def _hero_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        heroes = self.store.list_heroes()
        needle = current.strip().lower()
        prefix_matches: list[app_commands.Choice[str]] = []
        contains_matches: list[app_commands.Choice[str]] = []

        for hero in heroes:
            lowered = hero.name.lower()
            if not needle or lowered.startswith(needle):
                prefix_matches.append(app_commands.Choice(name=hero.name, value=hero.name))
            elif needle in lowered:
                contains_matches.append(app_commands.Choice(name=hero.name, value=hero.name))

        return (prefix_matches + contains_matches)[:25]

    @app_commands.command(
        name="counter",
        description="Recomienda el Top de ítems counter contra un héroe enemigo en Deadlock.",
    )
    @app_commands.describe(
        enemigo="Héroe enemigo que quieres contrarrestar",
        aliado="Tu héroe aliado (opcional)",
    )
    @app_commands.autocomplete(enemigo=_hero_autocomplete, aliado=_hero_autocomplete)
    async def counter_command(
        self,
        interaction: discord.Interaction,
        enemigo: str,
        aliado: str | None = None,
    ) -> None:
        started = time.perf_counter()
        try:
            data = self.store.get_counters(
                enemigo,
                ally_query=aliado,
                limit=self.default_limit,
                max_limit=self.max_limit,
            )
        except HeroNotFoundError as exc:
            suggestions_text = (
                f"\n¿Quisiste decir: {', '.join(f'**{s}**' for s in exc.suggestions)}?"
                if exc.suggestions
                else ""
            )
            await interaction.response.send_message(
                content=f"❌ {exc.message}{suggestions_text}",
                ephemeral=True,
            )
            return
        except StoreUnavailableError as exc:
            await interaction.response.send_message(
                content=f"⚠️ {exc}",
                ephemeral=True,
            )
            return
        except Exception:
            logger.exception("Unexpected error executing /counter enemigo=%s aliado=%s", enemigo, aliado)
            await interaction.response.send_message(
                content="⚠️ Ocurrió un error inesperado al consultar las recomendaciones.",
                ephemeral=True,
            )
            return

        embed = build_counter_embed(data)
        await interaction.response.send_message(embed=embed)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        logger.info(
            "Served /counter enemigo=%s aliado=%s fallback=%s in %.2f ms",
            enemigo,
            aliado,
            data.get("fallback"),
            elapsed_ms,
        )
