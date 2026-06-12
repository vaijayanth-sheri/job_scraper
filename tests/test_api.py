from __future__ import annotations

import time
from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient

from job_search import api
from job_search.scraper import SearchMetadata, SearchResult


def test_create_search_rejects_blank_keyword() -> None:
    client = TestClient(api.app)
    response = client.post(
        "/api/searches",
        json={
            "keyword": " ",
            "location": "Munich, Germany",
            "sources": ["linkedin"],
            "results_per_source": 5,
        },
    )

    assert response.status_code == 422


def test_search_lifecycle_with_mocked_scraper(
    monkeypatch: object,
    tmp_path: Path,
) -> None:
    client = TestClient(api.app)

    def fake_run_search(*_: object, **__: object) -> SearchResult:
        csv_path = tmp_path / "mock.csv"
        rows = pd.DataFrame(
            [
                {
                    "job_title": "Energy Data Analyst",
                    "company_name": "Grid Co",
                    "location": "Munich",
                    "posting_date": "2026-06-12",
                    "job_url": "https://example.com/job",
                    "source_website": "linkedin",
                    "employment_type": "fulltime",
                }
            ]
        )
        rows.to_csv(csv_path, index=False)
        metadata = SearchMetadata(
            source_counts={"linkedin": 1, "stepstone": 0},
            skipped_sources={"stepstone": "JobSpy does not support this source."},
            duplicates_removed=0,
            final_count=1,
            csv_filename=csv_path.name,
        )
        return SearchResult(jobs=rows, metadata=metadata, csv_path=csv_path)

    monkeypatch.setattr(api, "run_search", fake_run_search)
    response = client.post(
        "/api/searches",
        json={
            "keyword": "Energiedaten",
            "location": "Munich, Germany",
            "sources": ["linkedin", "stepstone"],
            "results_per_source": 5,
            "distance_km": 50,
            "hours_old": 24,
        },
    )

    assert response.status_code == 202
    job_id = response.json()["job_id"]

    status_payload = {}
    for _ in range(30):
        status_response = client.get(f"/api/searches/{job_id}")
        status_payload = status_response.json()
        if status_payload["status"] == "completed":
            break
        time.sleep(0.1)

    assert status_payload["status"] == "completed"

    results_response = client.get(f"/api/searches/{job_id}/results")
    assert results_response.status_code == 200
    results_payload = results_response.json()
    assert results_payload["rows"][0]["job_title"] == "Energy Data Analyst"
    assert "stepstone" in results_payload["metadata"]["skipped_sources"]

    csv_response = client.get(f"/api/searches/{job_id}/csv")
    assert csv_response.status_code == 200
    assert "job_title" in csv_response.text
