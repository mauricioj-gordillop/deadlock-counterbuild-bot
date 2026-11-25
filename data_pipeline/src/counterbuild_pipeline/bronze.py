"""Bronze layer readers: raw JSON ingestion with lineage metadata."""

from __future__ import annotations

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F


def read_raw_matches(spark: SparkSession, path: str) -> DataFrame:
    """Read newline-delimited match JSON files into raw Bronze records."""
    df = (
        spark.read.option("pathGlobFilter", "*.json*")
        .text(path)
        .select(
            F.col("value").alias("raw_json"),
            F.col("_metadata.file_path").alias("source_file"),
            F.current_timestamp().alias("ingested_at"),
        )
        .filter(F.length(F.trim(F.col("raw_json"))) > 0)
        .withColumn("match_id", F.get_json_object(F.col("raw_json"), "$.match_id").cast("long"))
    )
    return df.select("match_id", "raw_json", "source_file", "ingested_at")


def read_raw_reference(spark: SparkSession, path: str) -> DataFrame:
    """Read full-document reference JSON files (heroes.json / items.json) into Bronze."""
    df = (
        spark.read.option("wholetext", "true")
        .option("pathGlobFilter", "*.json")
        .text(path)
        .select(
            F.col("value").alias("raw_json"),
            F.col("_metadata.file_path").alias("source_file"),
            F.current_timestamp().alias("ingested_at"),
        )
        .filter(F.length(F.trim(F.col("raw_json"))) > 0)
    )
    return df
