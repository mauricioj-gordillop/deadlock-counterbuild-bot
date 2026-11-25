"""Configuration defaults for Databricks and local pipeline execution."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PipelineConfig:
    """Central configuration for Bronze, Silver, and Gold Delta tables and rules."""

    catalog: str = "workspace"
    schema: str = "deadlock"

    raw_matches_path: str = "/Volumes/workspace/deadlock/raw/matches"
    raw_reference_path: str = "/Volumes/workspace/deadlock/raw/reference"

    bronze_matches_table: str = "bronze_matches"
    bronze_reference_heroes_table: str = "bronze_reference_heroes"
    bronze_reference_items_table: str = "bronze_reference_items"

    silver_matches_table: str = "silver_matches"
    silver_player_matches_table: str = "silver_player_matches"
    silver_player_items_table: str = "silver_player_items"
    silver_dim_heroes_table: str = "silver_dim_heroes"
    silver_dim_items_table: str = "silver_dim_items"

    gold_counter_items_table: str = "gold_counter_items"

    min_duration_s: int = 900
    min_games_with_item: int = 50
    min_games_without_item: int = 50
    top_n_per_pair: int = 10
    max_purchase_time_s: int | None = None

    def fqn(self, table_name: str) -> str:
        """Return three-level Unity Catalog table name."""
        return f"{self.catalog}.{self.schema}.{table_name}"
