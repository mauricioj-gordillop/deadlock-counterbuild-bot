"""Fetch raw Deadlock match metadata JSONL files from api.deadlock-api.com."""

from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

try:
    from ingestion._http import build_headers, get_with_retries
except ImportError:
    from _http import build_headers, get_with_retries

MATCHES_METADATA_URL = "https://api.deadlock-api.com/v1/matches/metadata"
logger = logging.getLogger(__name__)


def unwrap_match_record(record: dict[str, Any]) -> dict[str, Any]:
    """Unwrap match_info envelope when present; leave flat records unchanged."""
    inner = record.get("match_info")
    if isinstance(inner, dict):
        return inner
    return record


def dump_record_schema(record: dict[str, Any]) -> None:
    """Print top-level, player-level, and item-level keys for schema inspection."""
    print("Match keys:", sorted(record.keys()))
    players = record.get("players")
    if isinstance(players, list) and players and isinstance(players[0], dict):
        first_player = players[0]
        print("Player[0] keys:", sorted(first_player.keys()))
        items = first_player.get("items")
        if isinstance(items, list) and items and isinstance(items[0], dict):
            print("Item[0] keys:", sorted(items[0].keys()))
        else:
            print("Item[0] keys: <no items found on Player[0]>")
    else:
        print("Player[0] keys: <no players found>")


def _extract_records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [unwrap_match_record(item) for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("matches", "data", "results"):
            val = payload.get(key)
            if isinstance(val, list):
                return [unwrap_match_record(item) for item in val if isinstance(item, dict)]
        return [unwrap_match_record(payload)]
    return []


def fetch_matches(
    *,
    out_dir: Path,
    limit_per_request: int = 100,
    pages: int = 5,
    min_unix_timestamp: int | None = None,
    api_key: str | None = None,
    timeout_s: float = 30.0,
    dump_schema: bool = False,
) -> list[Path]:
    """Paginate /v1/matches/metadata and write each page as JSONL."""
    out_dir.mkdir(parents=True, exist_ok=True)
    headers = build_headers(api_key)
    seen_match_ids: set[int] = set()
    written_files: list[Path] = []
    current_min_ts = min_unix_timestamp
    current_min_match_id: int | None = None
    dumped = False

    with requests.Session() as session:
        for page in range(1, pages + 1):
            params: dict[str, Any] = {
                "include_player_items": "true",
                "limit": limit_per_request,
            }
            if current_min_ts is not None:
                params["min_unix_timestamp"] = current_min_ts
            if current_min_match_id is not None:
                params["min_match_id"] = current_min_match_id

            logger.info("Fetching page %d/%d with params=%s", page, pages, params)
            resp = get_with_retries(
                session,
                MATCHES_METADATA_URL,
                params=params,
                headers=headers,
                timeout_s=timeout_s,
            )
            records = _extract_records(resp.json())
            if not records:
                logger.info("Empty response on page %d; stopping pagination.", page)
                break

            fresh_records: list[dict[str, Any]] = []
            max_match_id: int | None = None
            max_start_time: int | None = None
            for rec in records:
                mid = rec.get("match_id")
                if isinstance(mid, int):
                    if mid in seen_match_ids:
                        continue
                    seen_match_ids.add(mid)
                    max_match_id = mid if max_match_id is None else max(max_match_id, mid)
                st = rec.get("start_time")
                if isinstance(st, int):
                    max_start_time = st if max_start_time is None else max(max_start_time, st)
                fresh_records.append(rec)

            if dump_schema and not dumped and records:
                dump_record_schema(records[0])
                dumped = True

            if not fresh_records:
                logger.info("No new match_ids returned on page %d; stopping pagination.", page)
                break

            ts_slug = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            out_path = out_dir / f"matches_{ts_slug}_{page:04d}.jsonl"
            with out_path.open("w", encoding="utf-8") as fh:
                for rec in fresh_records:
                    fh.write(json.dumps(rec, separators=(",", ":")) + "\n")

            written_files.append(out_path)
            logger.info("Wrote %d matches to %s", len(fresh_records), out_path)

            if max_match_id is not None:
                current_min_match_id = max_match_id + 1
            elif max_start_time is not None:
                current_min_ts = max_start_time + 1

    return written_files


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Fetch raw Deadlock match metadata into JSONL files.")
    parser.add_argument("--limit-per-request", type=int, default=100, help="Matches requested per page")
    parser.add_argument("--pages", type=int, default=5, help="Maximum pages to fetch")
    parser.add_argument("--min-unix-timestamp", type=int, default=None, help="Filter matches >= Unix timestamp")
    parser.add_argument("--out", type=Path, default=Path("data/raw"), help="Output directory for JSONL files")
    parser.add_argument("--timeout", type=float, default=30.0, help="HTTP timeout in seconds")
    parser.add_argument(
        "--api-key",
        type=str,
        default=os.getenv("DEADLOCK_API_KEY") or None,
        help="Optional Deadlock API key (or set DEADLOCK_API_KEY)",
    )
    parser.add_argument(
        "--dump-schema",
        action="store_true",
        help="Print top-level, player, and item keys of the first fetched match",
    )
    args = parser.parse_args()
    fetch_matches(
        out_dir=args.out,
        limit_per_request=args.limit_per_request,
        pages=args.pages,
        min_unix_timestamp=args.min_unix_timestamp,
        api_key=args.api_key,
        timeout_s=args.timeout,
        dump_schema=args.dump_schema,
    )


if __name__ == "__main__":
    main()
