# Databricks notebook source
# MAGIC %md
# MAGIC # 03 - Gold Aggregate (1v1 Counter-Building Win-Rate Delta)
# MAGIC Computes per-`(ally_hero_id, enemy_hero_id, item_id)` win-rate delta in percentage points, including `ally_hero_id = 0` for any-ally queries, and optimizes Delta layout.

# COMMAND ----------

import sys
from pathlib import Path

for _candidate in (Path.cwd().parent / "src", Path.cwd() / "data_pipeline" / "src"):
    if (_candidate / "counterbuild_pipeline").is_dir() and str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

from counterbuild_pipeline import PipelineConfig, compute_counter_items

cfg = PipelineConfig()

# COMMAND ----------

player_matches = spark.table(cfg.fqn(cfg.silver_player_matches_table))
player_items = spark.table(cfg.fqn(cfg.silver_player_items_table))
dim_items = spark.table(cfg.fqn(cfg.silver_dim_items_table))
dim_heroes = spark.table(cfg.fqn(cfg.silver_dim_heroes_table))

gold_df = compute_counter_items(player_matches, player_items, dim_items, dim_heroes, cfg)

gold_table = cfg.fqn(cfg.gold_counter_items_table)
gold_df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(gold_table)

spark.sql(f"OPTIMIZE {gold_table} ZORDER BY (enemy_hero_id)")
print(f"Gold table {gold_table} ready with {spark.table(gold_table).count()} rules.")
