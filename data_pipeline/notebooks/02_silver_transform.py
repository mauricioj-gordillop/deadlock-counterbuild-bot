# Databricks notebook source
# MAGIC %md
# MAGIC # 02 - Silver Transform (Cleaning, Normalization & Exploding)
# MAGIC Parses Bronze JSON payloads, filters invalid/short/abandoned matches, deduplicates by `match_id`, and flattens player and item tables.

# COMMAND ----------

import sys
from pathlib import Path

for _candidate in (Path.cwd().parent / "src", Path.cwd() / "data_pipeline" / "src"):
    if (_candidate / "counterbuild_pipeline").is_dir() and str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

from counterbuild_pipeline import (
    PipelineConfig,
    build_dim_heroes,
    build_dim_items,
    clean_matches,
    explode_items,
    explode_players,
    parse_matches,
)

cfg = PipelineConfig()

# COMMAND ----------

bronze_matches = spark.table(cfg.fqn(cfg.bronze_matches_table))
bronze_heroes = spark.table(cfg.fqn(cfg.bronze_reference_heroes_table))
bronze_items = spark.table(cfg.fqn(cfg.bronze_reference_items_table))

dim_heroes = build_dim_heroes(bronze_heroes)
dim_items = build_dim_items(bronze_items)

parsed_matches = parse_matches(bronze_matches)
silver_matches = clean_matches(parsed_matches, cfg)
silver_player_matches = explode_players(silver_matches)
silver_player_items = explode_items(
    silver_matches, dim_items, max_purchase_time_s=cfg.max_purchase_time_s
)

# COMMAND ----------

tables = {
    cfg.fqn(cfg.silver_dim_heroes_table): dim_heroes,
    cfg.fqn(cfg.silver_dim_items_table): dim_items,
    cfg.fqn(cfg.silver_matches_table): silver_matches.drop("players"),
    cfg.fqn(cfg.silver_player_matches_table): silver_player_matches,
    cfg.fqn(cfg.silver_player_items_table): silver_player_items,
}

for table_name, df in tables.items():
    df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(table_name)
    print(f"Wrote {table_name}: {spark.table(table_name).count()} rows")
