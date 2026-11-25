"""Databricks SQL loader populating the in-memory CounterStore."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Protocol

from bot.config import BotSettings
from bot.names import HeroRecord, normalize_hero_name
from bot.store import CounterRuleRecord, CounterSnapshot, ItemRecord, build_snapshot

_SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class DataSource(Protocol):
    """Source capable of building an immutable CounterSnapshot."""

    def load_snapshot(self) -> CounterSnapshot:
        """Fetch heroes, items, and Gold counter rules synchronously (run via to_thread)."""


def _validate_identifier(name: str, label: str) -> str:
    cleaned = name.strip()
    if not _SAFE_IDENTIFIER_RE.match(cleaned):
        raise ValueError(f"Invalid Databricks {label} identifier: {name!r}")
    return cleaned


def _opt_int(val: Any) -> int | None:
    if val is None or str(val).strip() == "":
        return None
    return int(float(str(val).strip()))


def _opt_float(val: Any) -> float | None:
    if val is None or str(val).strip() == "":
        return None
    return float(str(val).strip())


def _parse_ts(val: Any) -> datetime | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val if val.tzinfo is not None else val.replace(tzinfo=timezone.utc)
    text = str(val).strip()
    if not text:
        return None
    dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


class DatabricksDataSource:
    """Loads Silver dimensions and Gold counter rules from a Databricks SQL Warehouse."""

    def __init__(
        self,
        *,
        server_hostname: str,
        http_path: str,
        access_token: str,
        catalog: str = "workspace",
        schema: str = "deadlock",
    ) -> None:
        if not (server_hostname and http_path and access_token):
            raise ValueError(
                "DATABRICKS_SERVER_HOSTNAME, DATABRICKS_HTTP_PATH, and DATABRICKS_TOKEN are required."
            )
        self.server_hostname = server_hostname
        self.http_path = http_path
        self.access_token = access_token
        self.catalog = _validate_identifier(catalog, "catalog")
        self.schema = _validate_identifier(schema, "schema")

    def load_snapshot(self) -> CounterSnapshot:
        from databricks import sql as dbsql

        prefix = f"{self.catalog}.{self.schema}"
        with dbsql.connect(
            server_hostname=self.server_hostname,
            http_path=self.http_path,
            access_token=self.access_token,
        ) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT hero_id, name, name_normalized FROM {prefix}.silver_dim_heroes"
                )
                heroes = [
                    HeroRecord(
                        hero_id=int(r[0]),
                        name=str(r[1]).strip(),
                        name_normalized=normalize_hero_name(str(r[2] or r[1])),
                    )
                    for r in cur.fetchall()
                ]

                cur.execute(
                    f"SELECT item_id, name, cost, tier, slot_type FROM {prefix}.silver_dim_items"
                )
                items = [
                    ItemRecord(
                        item_id=int(r[0]),
                        name=str(r[1]).strip(),
                        cost=_opt_int(r[2]),
                        tier=_opt_int(r[3]),
                        slot_type=str(r[4]).strip().lower() if r[4] else None,
                    )
                    for r in cur.fetchall()
                ]

                cur.execute(
                    f"""
                    SELECT ally_hero_id, enemy_hero_id, item_id,
                           win_rate_delta, win_rate_with_item, games_with_item,
                           rank, computed_at
                    FROM {prefix}.gold_counter_items
                    """
                )
                counters = [
                    CounterRuleRecord(
                        ally_hero_id=int(r[0]),
                        enemy_hero_id=int(r[1]),
                        item_id=int(r[2]),
                        win_rate_delta=round(float(r[3]), 2),
                        win_rate_with_item=_opt_float(r[4]),
                        games_with_item=int(r[5]),
                        rank=int(r[6]),
                        computed_at=_parse_ts(r[7]),
                    )
                    for r in cur.fetchall()
                ]

        return build_snapshot(
            heroes=heroes,
            items=items,
            counters=counters,
            source=f"databricks:{prefix}",
        )


def build_data_source(settings: BotSettings) -> DataSource:
    """Instantiate the Databricks DataSource."""
    return DatabricksDataSource(
        server_hostname=settings.databricks_server_hostname,
        http_path=settings.databricks_http_path,
        access_token=settings.databricks_token,
        catalog=settings.databricks_catalog,
        schema=settings.databricks_schema,
    )
