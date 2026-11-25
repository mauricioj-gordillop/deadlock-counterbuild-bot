# Databricks notebook source
# MAGIC %md
# MAGIC # 01 - Bronze Ingest (Raw JSON -> Delta Lake)
# MAGIC Reads raw Deadlock match JSONL files and static reference JSON files from Unity Catalog Volumes into Bronze Delta tables.

# COMMAND ----------

import sys
from pathlib import Path

for _candidate in (Path.cwd().parent / "src", Path.cwd() / "data_pipeline" / "src"):
    if (_candidate / "counterbuild_pipeline").is_dir() and str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

from counterbuild_pipeline import PipelineConfig, read_raw_matches, read_raw_reference

cfg = PipelineConfig()

# COMMAND ----------

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {cfg.catalog}.{cfg.schema}")
spark.sql(f"CREATE VOLUME IF NOT EXISTS {cfg.catalog}.{cfg.schema}.raw")

# COMMAND ----------

bronze_matches_df = read_raw_matches(spark, cfg.raw_matches_path)
matches_table = cfg.fqn(cfg.bronze_matches_table)

if spark.catalog.tableExists(matches_table):
    bronze_matches_df.createOrReplaceTempView("incoming_bronze_matches")
    spark.sql(
        f"""
        MERGE INTO {matches_table} AS target
        USING (
            SELECT match_id, raw_json, source_file, ingested_at
            FROM (
                SELECT *, ROW_NUMBER() OVER (PARTITION BY match_id ORDER BY ingested_at DESC) AS rn
                FROM incoming_bronze_matches
                WHERE match_id IS NOT NULL
            )
            WHERE rn = 1
        ) AS src
        ON target.match_id = src.match_id
        WHEN NOT MATCHED THEN INSERT *
        """
    )
else:
    (
        bronze_matches_df.write.format("delta")
        .mode("overwrite")
        .saveAsTable(matches_table)
    )

print(f"Bronze matches count: {spark.table(matches_table).count()}")

# COMMAND ----------

heroes_ref_df = read_raw_reference(spark, f"{cfg.raw_reference_path}/heroes.json")
heroes_ref_df.write.format("delta").mode("overwrite").saveAsTable(cfg.fqn(cfg.bronze_reference_heroes_table))

items_ref_df = read_raw_reference(spark, f"{cfg.raw_reference_path}/items.json")
items_ref_df.write.format("delta").mode("overwrite").saveAsTable(cfg.fqn(cfg.bronze_reference_items_table))

print("Reference Bronze snapshots updated.")
