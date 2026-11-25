"""Download static Deadlock hero and item metadata from api.deadlock-api.com/v1/assets."""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path

import requests

try:
    from ingestion._http import build_headers, get_with_retries
except ImportError:
    from _http import build_headers, get_with_retries

ASSETS_BASE_URL = "https://api.deadlock-api.com/v1/assets"
REFERENCE_ENDPOINTS = {
    "heroes.json": f"{ASSETS_BASE_URL}/heroes",
    "items.json": f"{ASSETS_BASE_URL}/items",
}

logger = logging.getLogger(__name__)


def fetch_reference(out_dir: Path, api_key: str | None = None, timeout_s: float = 30.0) -> list[Path]:
    """Download raw heroes and items JSON files into out_dir."""
    out_dir.mkdir(parents=True, exist_ok=True)
    headers = build_headers(api_key)
    written: list[Path] = []

    with requests.Session() as session:
        for filename, url in REFERENCE_ENDPOINTS.items():
            logger.info("Fetching %s -> %s", url, out_dir / filename)
            resp = get_with_retries(session, url, headers=headers, timeout_s=timeout_s)
            dest = out_dir / filename
            dest.write_bytes(resp.content)
            written.append(dest)
            logger.info("Saved %s (%d bytes)", dest, len(resp.content))

    return written


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Fetch Deadlock static reference data (heroes & items).")
    parser.add_argument("--out", type=Path, default=Path("data/reference"), help="Output directory")
    parser.add_argument("--timeout", type=float, default=30.0, help="HTTP timeout in seconds")
    parser.add_argument(
        "--api-key",
        type=str,
        default=os.getenv("DEADLOCK_API_KEY") or None,
        help="Optional Deadlock API key",
    )
    args = parser.parse_args()
    fetch_reference(args.out, api_key=args.api_key, timeout_s=args.timeout)


if __name__ == "__main__":
    main()
