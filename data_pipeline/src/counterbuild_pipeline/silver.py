"""Silver layer transformations: parsing, validation, deduplication, and flattening."""

from __future__ import annotations

from pyspark.sql import Column, DataFrame, Window
from pyspark.sql import functions as F
from pyspark.sql.types import ArrayType

from counterbuild_pipeline.config import PipelineConfig
from counterbuild_pipeline.schemas import HERO_REF_SCHEMA, ITEM_REF_SCHEMA, MATCH_SCHEMA


def normalize_team(col: Column) -> Column:
    """Map Deadlock team encodings ('Team0', '0', 'k_ECitadelLobbyTeam_Team0', ...) to 0/1/null."""
    cleaned = F.lower(F.trim(col.cast("string")))
    return (
        F.when(cleaned.rlike(r"^(?:.*team_?)?0$"), F.lit(0))
        .when(cleaned.rlike(r"^(?:.*team_?)?1$"), F.lit(1))
        .otherwise(F.lit(None).cast("int"))
    )


def normalize_start_time(col: Column) -> Column:
    """Parse Unix epoch integers or UTC datetime strings safely under Spark ANSI mode."""
    trimmed = F.trim(col.cast("string"))
    return (
        F.when(trimmed.isNull() | (trimmed == F.lit("")), F.lit(None).cast("long"))
        .when(trimmed.rlike(r"^\d+$"), trimmed.cast("long"))
        .otherwise(F.unix_timestamp(F.try_to_timestamp(trimmed)))
    )


def normalize_name_column(col: Column) -> Column:
    """Normalize hero/item display names consistently with the OLTP API lookup."""
    accents_from = "áàäâãéèëêíìïîóòöôõúùüûñç"
    accents_to = "aaaaaeeeeiiiiooooouuuunc"
    lowered = F.lower(F.trim(col))
    ascii_approx = F.translate(lowered, accents_from, accents_to)
    return F.regexp_replace(ascii_approx, r"[^a-z0-9]", "")


def parse_matches(bronze_df: DataFrame) -> DataFrame:
    """Parse raw JSON strings from Bronze using the canonical MATCH_SCHEMA."""
    ingested_col = (
        F.col("ingested_at") if "ingested_at" in bronze_df.columns else F.current_timestamp()
    )
    parsed = bronze_df.select(
        F.from_json(F.col("raw_json"), MATCH_SCHEMA).alias("m"),
        ingested_col.alias("ingested_at"),
    )
    return parsed.select(
        F.col("m.match_id").alias("match_id"),
        F.col("m.start_time").alias("start_time"),
        F.col("m.duration_s").alias("duration_s"),
        F.col("m.winning_team").alias("winning_team"),
        F.col("m.game_mode").alias("game_mode"),
        F.col("m.not_scored").alias("not_scored"),
        F.col("m.players").alias("players"),
        F.col("ingested_at"),
    )


def clean_matches(parsed_df: DataFrame, cfg: PipelineConfig) -> DataFrame:
    """Filter invalid/abandoned/incomplete matches and deduplicate by match_id."""
    normalized = parsed_df.withColumn(
        "winning_team_norm", normalize_team(F.col("winning_team"))
    ).withColumn("start_time_norm", normalize_start_time(F.col("start_time")))

    valid = normalized.filter(
        F.col("match_id").isNotNull()
        & F.col("start_time_norm").isNotNull()
        & (~F.coalesce(F.col("not_scored"), F.lit(False)))
        & (F.col("duration_s") >= F.lit(cfg.min_duration_s))
        & F.col("winning_team_norm").isNotNull()
        & F.col("players").isNotNull()
        & (F.size(F.col("players")) == F.lit(12))
        & (
            ~F.exists(
                F.col("players"),
                lambda p: F.coalesce(p["abandon_match_time_s"], F.lit(0)) > F.lit(0),
            )
        )
        & F.forall(
            F.col("players"),
            lambda p: normalize_team(p["team"]).isNotNull()
            & p["hero_id"].isNotNull()
            & p["account_id"].isNotNull(),
        )
    )

    dedup_window = Window.partitionBy("match_id").orderBy(F.col("ingested_at").desc_nulls_last())
    deduped = (
        valid.withColumn("_rn", F.row_number().over(dedup_window))
        .filter(F.col("_rn") == F.lit(1))
        .drop("_rn")
    )

    return deduped.select(
        F.col("match_id"),
        F.col("start_time_norm").alias("start_time"),
        F.col("duration_s"),
        F.col("winning_team_norm").alias("winning_team"),
        F.col("game_mode"),
        F.col("players"),
        F.col("ingested_at"),
    )


def explode_players(clean_matches_df: DataFrame) -> DataFrame:
    """Flatten one row per (match_id, player) with normalized team and win flag."""
    exploded = clean_matches_df.select(
        F.col("match_id"),
        F.col("winning_team"),
        F.explode(F.col("players")).alias("p"),
    )
    with_team = exploded.select(
        F.col("match_id"),
        F.col("p.account_id").cast("long").alias("account_id"),
        F.col("p.player_slot").cast("int").alias("player_slot"),
        normalize_team(F.col("p.team")).alias("team"),
        F.col("p.hero_id").cast("int").alias("hero_id"),
        F.col("winning_team"),
    )
    return with_team.select(
        "match_id",
        "account_id",
        "player_slot",
        "team",
        "hero_id",
        (F.col("team") == F.col("winning_team")).alias("won"),
    )


def explode_items(
    clean_matches_df: DataFrame,
    dim_items_df: DataFrame,
    max_purchase_time_s: int | None = None,
) -> DataFrame:
    """Flatten shop-item purchases per (match_id, account_id, item_id), keeping earliest purchase."""
    players_exploded = clean_matches_df.select(
        F.col("match_id"),
        F.explode(F.col("players")).alias("p"),
    ).select(
        F.col("match_id"),
        F.col("p.account_id").cast("long").alias("account_id"),
        F.col("p.items").alias("items"),
    )

    items_exploded = players_exploded.filter(F.col("items").isNotNull()).select(
        F.col("match_id"),
        F.col("account_id"),
        F.explode(F.col("items")).alias("it"),
    ).select(
        F.col("match_id"),
        F.col("account_id"),
        F.coalesce(F.col("it.item_id"), F.col("it.upgrade_id")).cast("long").alias("item_id"),
        F.coalesce(F.col("it.game_time_s"), F.lit(0)).cast("int").alias("game_time_s"),
    )

    if max_purchase_time_s is not None:
        items_exploded = items_exploded.filter(F.col("game_time_s") <= F.lit(max_purchase_time_s))

    shop_items = dim_items_df.select("item_id").distinct()
    filtered = items_exploded.filter(F.col("item_id").isNotNull()).join(
        shop_items, on="item_id", how="inner"
    )

    return filtered.groupBy("match_id", "account_id", "item_id").agg(
        F.min("game_time_s").alias("game_time_s")
    )


def build_dim_heroes(bronze_heroes_df: DataFrame) -> DataFrame:
    """Parse heroes reference JSON array into deduplicated Silver hero dimension."""
    parsed = bronze_heroes_df.select(
        F.explode(F.from_json(F.col("raw_json"), ArrayType(HERO_REF_SCHEMA))).alias("h")
    ).select("h.*")

    filtered = parsed.filter(
        F.col("id").isNotNull()
        & F.col("name").isNotNull()
        & F.coalesce(F.col("player_selectable"), F.lit(True))
    )

    dedup_w = Window.partitionBy("id").orderBy(F.col("name").asc())
    return (
        filtered.withColumn("_rn", F.row_number().over(dedup_w))
        .filter(F.col("_rn") == 1)
        .select(
            F.col("id").cast("int").alias("hero_id"),
            F.trim(F.col("name")).alias("name"),
            normalize_name_column(F.col("name")).alias("name_normalized"),
        )
    )


def build_dim_items(bronze_items_df: DataFrame) -> DataFrame:
    """Parse items reference JSON array, keeping only purchasable shop upgrades."""
    parsed = bronze_items_df.select(
        F.explode(F.from_json(F.col("raw_json"), ArrayType(ITEM_REF_SCHEMA))).alias("it")
    ).select("it.*")

    filtered = parsed.filter(
        F.col("id").isNotNull()
        & F.col("name").isNotNull()
        & (F.lower(F.col("type")) == F.lit("upgrade"))
        & (F.col("shopable") == F.lit(True))
    )

    dedup_w = Window.partitionBy("id").orderBy(F.col("name").asc())
    return (
        filtered.withColumn("_rn", F.row_number().over(dedup_w))
        .filter(F.col("_rn") == 1)
        .select(
            F.col("id").cast("long").alias("item_id"),
            F.trim(F.col("name")).alias("name"),
            F.col("cost").cast("int").alias("cost"),
            F.col("item_tier").cast("smallint").alias("tier"),
            F.lower(F.trim(F.col("item_slot_type"))).alias("slot_type"),
        )
    )
