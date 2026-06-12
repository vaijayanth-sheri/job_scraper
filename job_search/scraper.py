from __future__ import annotations

import csv
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import pandas as pd
import yaml
from jobspy import scrape_jobs


CONFIG_PATH = Path("config.yaml")
OUTPUT_DIR = Path("output")
RUNTIME_SEARCH_DIR = Path("runtime") / "searches"
OUTPUT_COLUMNS = [
    "job_title",
    "company_name",
    "location",
    "posting_date",
    "job_url",
    "source_website",
    "employment_type",
]
JOBSPY_SOURCE_COLUMNS = {
    "title": "job_title",
    "company": "company_name",
    "location": "location",
    "date_posted": "posting_date",
    "job_url": "job_url",
    "site": "source_website",
    "job_type": "employment_type",
}
SUPPORTED_JOBSPY_SOURCES = {"linkedin", "indeed"}
ALLOWED_CONFIG_SOURCES = SUPPORTED_JOBSPY_SOURCES | {"stepstone"}
DEFAULT_TIMEOUT_SECONDS = 180

ScrapeFunction = Callable[..., pd.DataFrame]


@dataclass(frozen=True)
class SearchConfig:
    sources: list[str]
    country: str
    results_per_source: int


@dataclass(frozen=True)
class SearchParams:
    keyword: str
    location: str
    sources: list[str]
    results_per_source: int
    distance_km: int = 50
    hours_old: int | None = None
    country_indeed: str = "germany"
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS


@dataclass
class SearchMetadata:
    source_counts: dict[str, int] = field(default_factory=dict)
    skipped_sources: dict[str, str] = field(default_factory=dict)
    source_errors: dict[str, str] = field(default_factory=dict)
    duplicates_removed: int = 0
    final_count: int = 0
    csv_filename: str | None = None
    timed_out: bool = False


@dataclass
class SearchResult:
    jobs: pd.DataFrame
    metadata: SearchMetadata
    csv_path: Path


def load_config(path: Path) -> SearchConfig:
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with path.open("r", encoding="utf-8") as file:
        raw_config: dict[str, Any] = yaml.safe_load(file) or {}

    sources = raw_config.get("sources")
    country = raw_config.get("country")
    results_per_source = raw_config.get("results_per_source")

    if not isinstance(sources, list) or not all(isinstance(item, str) for item in sources):
        raise ValueError("config.yaml must define sources as a list of source names.")
    if not isinstance(country, str) or not country.strip():
        raise ValueError("config.yaml must define country as a non-empty string.")
    if not isinstance(results_per_source, int) or results_per_source <= 0:
        raise ValueError("config.yaml must define results_per_source as a positive integer.")

    normalized_sources = normalize_sources(sources)
    return SearchConfig(
        sources=normalized_sources,
        country=country.strip(),
        results_per_source=results_per_source,
    )


def normalize_sources(sources: list[str]) -> list[str]:
    normalized_sources = [source.strip().lower() for source in sources if source.strip()]
    if not normalized_sources:
        raise ValueError("At least one source must be configured.")

    unsupported_sources = sorted(set(normalized_sources) - ALLOWED_CONFIG_SOURCES)
    if unsupported_sources:
        allowed = ", ".join(sorted(ALLOWED_CONFIG_SOURCES))
        unsupported = ", ".join(unsupported_sources)
        raise ValueError(f"Unsupported source(s): {unsupported}. Allowed sources: {allowed}.")

    return normalized_sources


def filename_from_keyword(keyword: str, suffix: str = "") -> str:
    clean_keyword = re.sub(r"[^A-Za-z0-9]+", "_", keyword.strip()).strip("_")
    clean_suffix = re.sub(r"[^A-Za-z0-9]+", "_", suffix.strip()).strip("_")
    parts = [part for part in [clean_keyword or "jobs", clean_suffix] if part]
    return f"{'_'.join(parts)}.csv"


def build_search_params(
    keyword: str,
    location: str,
    sources: list[str],
    results_per_source: int,
    distance_km: int = 50,
    hours_old: int | None = None,
    country_indeed: str = "germany",
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> SearchParams:
    if not keyword.strip():
        raise ValueError("Keyword is required.")
    if not location.strip():
        raise ValueError("Location is required.")
    if results_per_source <= 0:
        raise ValueError("results_per_source must be positive.")
    if distance_km < 0:
        raise ValueError("distance_km must be zero or greater.")
    if hours_old is not None and hours_old <= 0:
        raise ValueError("hours_old must be positive when provided.")

    return SearchParams(
        keyword=keyword.strip(),
        location=location.strip(),
        sources=normalize_sources(sources),
        results_per_source=results_per_source,
        distance_km=distance_km,
        hours_old=hours_old,
        country_indeed=country_indeed,
        timeout_seconds=timeout_seconds,
    )


def fetch_source_jobs(
    params: SearchParams,
    source: str,
    scrape_func: ScrapeFunction = scrape_jobs,
) -> pd.DataFrame:
    jobs = scrape_func(
        site_name=source,
        search_term=params.keyword,
        location=params.location,
        distance=params.distance_km,
        results_wanted=params.results_per_source,
        country_indeed=params.country_indeed,
        hours_old=params.hours_old,
        verbose=0,
    )
    if jobs is None:
        return pd.DataFrame()
    return jobs


def collect_jobs(
    params: SearchParams,
    scrape_func: ScrapeFunction = scrape_jobs,
) -> tuple[pd.DataFrame, SearchMetadata]:
    frames: list[pd.DataFrame] = []
    metadata = SearchMetadata()
    started_at = time.monotonic()

    for source in params.sources:
        if time.monotonic() - started_at > params.timeout_seconds:
            metadata.timed_out = True
            metadata.source_errors[source] = "Search timed out before this source started."
            logging.warning("%s: skipped because the search timed out.", source)
            continue

        if source not in SUPPORTED_JOBSPY_SOURCES:
            reason = "JobSpy does not support this source."
            metadata.skipped_sources[source] = reason
            metadata.source_counts[source] = 0
            logging.warning("%s: skipped because %s", source, reason)
            continue

        try:
            jobs = fetch_source_jobs(params, source, scrape_func)
        except Exception as exc:
            metadata.source_counts[source] = 0
            metadata.source_errors[source] = str(exc)
            logging.error("%s: search failed: %s", source, exc)
            continue

        metadata.source_counts[source] = len(jobs)
        logging.info("%s: %s jobs found", source, len(jobs))
        if not jobs.empty:
            frames.append(jobs)

    if not frames:
        return pd.DataFrame(), metadata

    return pd.concat(frames, ignore_index=True), metadata


def standardize_columns(jobs: pd.DataFrame) -> pd.DataFrame:
    standardized = pd.DataFrame()

    for source_column, output_column in JOBSPY_SOURCE_COLUMNS.items():
        if source_column in jobs.columns:
            standardized[output_column] = jobs[source_column]
        else:
            standardized[output_column] = pd.NA

    standardized["posting_date"] = pd.to_datetime(
        standardized["posting_date"], errors="coerce"
    ).dt.date
    for column in [
        "job_url",
        "job_title",
        "company_name",
        "location",
        "source_website",
        "employment_type",
    ]:
        standardized[column] = standardized[column].astype("string").str.strip()

    return standardized[OUTPUT_COLUMNS]


def remove_invalid_and_duplicates(jobs: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    with_valid_urls = jobs[
        jobs["job_url"].notna() & jobs["job_url"].str.match(r"^https?://", na=False)
    ].copy()

    before_dedupe = len(with_valid_urls)
    deduped = with_valid_urls.drop_duplicates(
        subset=["job_url"], keep="first", ignore_index=True
    )
    duplicates_removed = before_dedupe - len(deduped)

    return deduped, duplicates_removed


def sort_jobs(jobs: pd.DataFrame) -> pd.DataFrame:
    sortable = jobs.copy()
    sortable["_posting_date_sort"] = pd.to_datetime(
        sortable["posting_date"], errors="coerce"
    )
    sorted_jobs = sortable.sort_values(
        by=["_posting_date_sort", "job_title"],
        ascending=[False, True],
        na_position="last",
        kind="mergesort",
    )
    return sorted_jobs.drop(columns=["_posting_date_sort"])


def export_jobs(jobs: pd.DataFrame, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    jobs.to_csv(
        output_path,
        index=False,
        quoting=csv.QUOTE_NONNUMERIC,
        escapechar="\\",
    )
    return output_path


def run_search(
    params: SearchParams,
    output_dir: Path,
    scrape_func: ScrapeFunction = scrape_jobs,
    filename_suffix: str = "",
) -> SearchResult:
    raw_jobs, metadata = collect_jobs(params, scrape_func)
    standardized_jobs = standardize_columns(raw_jobs)
    clean_jobs, duplicates_removed = remove_invalid_and_duplicates(standardized_jobs)
    sorted_jobs = sort_jobs(clean_jobs)

    csv_filename = filename_from_keyword(params.keyword, filename_suffix)
    csv_path = export_jobs(sorted_jobs, output_dir / csv_filename)

    metadata.duplicates_removed = duplicates_removed
    metadata.final_count = len(sorted_jobs)
    metadata.csv_filename = csv_filename

    logging.info("Duplicates removed: %s", duplicates_removed)
    logging.info("Final jobs exported: %s", len(sorted_jobs))
    logging.info("CSV written to: %s", csv_path)

    return SearchResult(jobs=sorted_jobs, metadata=metadata, csv_path=csv_path)


def dataframe_to_records(jobs: pd.DataFrame) -> list[dict[str, Any]]:
    if jobs.empty:
        return []
    normalized = jobs.where(pd.notna(jobs), None)
    return normalized.to_dict(orient="records")
