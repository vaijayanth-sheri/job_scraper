from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from job_search.scraper import CONFIG_PATH, OUTPUT_DIR, build_search_params, load_config, run_search


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Search German job postings with JobSpy and export them to CSV."
    )
    parser.add_argument("keyword", help='Single search keyword, e.g. "Energy Data Analyst"')
    parser.add_argument(
        "--location",
        default=None,
        help="Search location. Defaults to the country configured in config.yaml.",
    )
    parser.add_argument(
        "--distance-km",
        type=int,
        default=50,
        help="Search radius in kilometers. Defaults to 50.",
    )
    parser.add_argument(
        "--hours-old",
        type=int,
        default=None,
        help="Only return jobs posted within this many hours when supported.",
    )
    parser.add_argument(
        "--config",
        default=str(CONFIG_PATH),
        help="Path to the YAML config file. Defaults to config.yaml.",
    )
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args = parse_args()

    try:
        config = load_config(Path(args.config))
        params = build_search_params(
            keyword=args.keyword,
            location=args.location or config.country,
            sources=config.sources,
            results_per_source=config.results_per_source,
            distance_km=args.distance_km,
            hours_old=args.hours_old,
            country_indeed=config.country.lower(),
        )
        run_search(params, OUTPUT_DIR)
    except Exception as exc:
        logging.error("Job search failed: %s", exc)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
