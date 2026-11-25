"""Unified Discord Bot entrypoint loading Databricks Gold rules into RAM with periodic refresh."""

from __future__ import annotations

import asyncio
import logging

import discord
from discord.ext import commands, tasks

from bot.cogs.counter import CounterCog
from bot.config import BotSettings, get_bot_settings
from bot.datasource import DataSource, build_data_source
from bot.health import HealthServer
from bot.store import CounterStore

logger = logging.getLogger(__name__)


class CounterBot(commands.Bot):
    """Single-process Discord Bot with in-memory Databricks snapshot and /health server."""

    def __init__(
        self,
        settings: BotSettings,
        *,
        store: CounterStore | None = None,
        data_source: DataSource | None = None,
    ) -> None:
        super().__init__(command_prefix="!", intents=discord.Intents.default())
        self.settings = settings
        self.store = store or CounterStore()
        self.data_source = data_source or build_data_source(settings)
        self.health_server = (
            HealthServer(self.store, port=settings.health_port)
            if settings.health_port > 0
            else None
        )
        self._refresh_loop = tasks.loop(hours=max(0.25, settings.refresh_interval_hours))(
            self._periodic_refresh
        )

    async def refresh_store(self) -> None:
        """Fetch a fresh snapshot in a worker thread and swap it atomically in RAM."""
        snapshot = await asyncio.to_thread(self.data_source.load_snapshot)
        self.store.update_snapshot(snapshot)
        logger.info(
            "Loaded snapshot from %s: %d heroes, %d counter rules",
            snapshot.source,
            len(snapshot.heroes),
            snapshot.total_rules,
        )

    async def _periodic_refresh(self) -> None:
        try:
            await self.refresh_store()
        except Exception:
            logger.exception(
                "Periodic snapshot refresh failed; keeping previous snapshot in RAM."
            )

    async def setup_hook(self) -> None:
        if self.health_server is not None:
            await self.health_server.start()
            logger.info("Health endpoint listening on port %s", self.health_server.bound_port)

        await self.refresh_store()
        self._refresh_loop.start()

        await self.add_cog(
            CounterCog(
                self,
                self.store,
                default_limit=self.settings.default_limit,
                max_limit=self.settings.max_limit,
            )
        )
        if self.settings.discord_guild_id:
            guild = discord.Object(id=self.settings.discord_guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            logger.info("Synced /counter command to guild %s", self.settings.discord_guild_id)
        else:
            await self.tree.sync()
            logger.info("Synced /counter command globally")

    async def on_ready(self) -> None:
        logger.info("Logged in as %s (id=%s)", self.user, getattr(self.user, "id", None))

    async def close(self) -> None:
        if self._refresh_loop.is_running():
            self._refresh_loop.cancel()
        if self.health_server is not None:
            await self.health_server.stop()
        await super().close()


def main() -> None:
    settings = get_bot_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    if not settings.discord_token or settings.discord_token == "your_discord_bot_token_here":
        raise SystemExit("DISCORD_TOKEN is not configured. Set it in .env before running the bot.")

    bot = CounterBot(settings)
    bot.run(settings.discord_token, log_handler=None)


if __name__ == "__main__":
    main()
