from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from job_search.scraper import (
    build_search_params,
    filename_from_keyword,
    normalize_sources,
    remove_invalid_and_duplicates,
    run_search,
    sort_jobs,
    standardize_columns,
)


def test_filename_from_keyword() -> None:
    assert filename_from_keyword("Energy Data Analyst") == "Energy_Data_Analyst.csv"
    assert filename_from_keyword("Energiedaten", "abc123") == "Energiedaten_abc123.csv"


def test_normalize_sources_rejects_unknown_source() -> None:
    with pytest.raises(ValueError, match="Unsupported source"):
        normalize_sources(["linkedin", "glassdoor"])


def test_standardize_filter_dedupe_and_sort() -> None:
    raw_jobs = pd.DataFrame(
        [
            {
                "title": "B Role",
                "company": "Beta",
                "location": "Munich",
                "date_posted": "2026-06-11",
                "job_url": "https://example.com/b",
                "site": "linkedin",
                "job_type": "fulltime",
            },
            {
                "title": "A Role",
                "company": "Alpha",
                "location": "Berlin",
                "date_posted": "2026-06-12",
                "job_url": "https://example.com/a",
                "site": "indeed",
                "job_type": None,
            },
            {
                "title": "Duplicate Role",
                "company": "Alpha",
                "location": "Berlin",
                "date_posted": "2026-06-12",
                "job_url": "https://example.com/a",
                "site": "indeed",
                "job_type": None,
            },
            {
                "title": "Missing URL",
                "company": "Nope",
                "location": "Berlin",
                "date_posted": "2026-06-12",
                "job_url": "",
                "site": "indeed",
                "job_type": None,
            },
        ]
    )

    standardized = standardize_columns(raw_jobs)
    deduped, duplicates_removed = remove_invalid_and_duplicates(standardized)
    sorted_jobs = sort_jobs(deduped)

    assert duplicates_removed == 1
    assert list(sorted_jobs["job_title"]) == ["A Role", "B Role"]
    assert list(sorted_jobs.columns) == [
        "job_title",
        "company_name",
        "location",
        "posting_date",
        "job_url",
        "source_website",
        "employment_type",
    ]


def test_run_search_reports_stepstone_skipped(tmp_path: Path) -> None:
    params = build_search_params(
        keyword="Energiedaten",
        location="Munich, Germany",
        sources=["linkedin", "stepstone"],
        results_per_source=10,
    )

    def fake_scrape_jobs(**_: object) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "title": "Energy Data Analyst",
                    "company": "Grid Co",
                    "location": "Munich",
                    "date_posted": "2026-06-12",
                    "job_url": "https://example.com/job",
                    "site": "linkedin",
                    "job_type": "fulltime",
                }
            ]
        )

    result = run_search(params, tmp_path, scrape_func=fake_scrape_jobs)

    assert result.metadata.source_counts["linkedin"] == 1
    assert result.metadata.source_counts["stepstone"] == 0
    assert "stepstone" in result.metadata.skipped_sources
    assert result.metadata.final_count == 1
    assert result.csv_path.exists()
