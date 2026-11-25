"""Explicit Spark StructType schemas for Deadlock match metadata and reference assets."""

from __future__ import annotations

from pyspark.sql.types import (
    ArrayType,
    BooleanType,
    IntegerType,
    LongType,
    StringType,
    StructField,
    StructType,
)

ITEM_EVENT_SCHEMA = StructType(
    [
        StructField("game_time_s", IntegerType(), True),
        StructField("item_id", LongType(), True),
        StructField("upgrade_id", LongType(), True),
        StructField("sold_time_s", IntegerType(), True),
        StructField("flags", IntegerType(), True),
        StructField("imbued_ability_id", LongType(), True),
    ]
)

PLAYER_SCHEMA = StructType(
    [
        StructField("account_id", LongType(), True),
        StructField("player_slot", IntegerType(), True),
        # Stored as StringType so from_json handles both "Team0"/"Team1" and 0/1 uniformly
        StructField("team", StringType(), True),
        StructField("hero_id", IntegerType(), True),
        StructField("abandon_match_time_s", IntegerType(), True),
        StructField("items", ArrayType(ITEM_EVENT_SCHEMA), True),
    ]
)

MATCH_SCHEMA = StructType(
    [
        StructField("match_id", LongType(), True),
        # Stored as StringType to handle both integer Unix timestamps and UTC datetime strings
        StructField("start_time", StringType(), True),
        StructField("duration_s", IntegerType(), True),
        StructField("winning_team", StringType(), True),
        StructField("game_mode", StringType(), True),
        StructField("not_scored", BooleanType(), True),
        StructField("players", ArrayType(PLAYER_SCHEMA), True),
    ]
)

HERO_REF_SCHEMA = StructType(
    [
        StructField("id", IntegerType(), True),
        StructField("name", StringType(), True),
        StructField("player_selectable", BooleanType(), True),
    ]
)

ITEM_REF_SCHEMA = StructType(
    [
        StructField("id", LongType(), True),
        StructField("name", StringType(), True),
        StructField("type", StringType(), True),
        StructField("shopable", BooleanType(), True),
        StructField("cost", IntegerType(), True),
        StructField("item_tier", IntegerType(), True),
        StructField("item_slot_type", StringType(), True),
    ]
)
