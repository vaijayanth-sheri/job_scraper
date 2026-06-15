import urllib.parse
from typing import Any
import pandas as pd
import httpx
from bs4 import BeautifulSoup

from job_search.adapters.base import JobAdapter


class ArbeitsagenturAdapter(JobAdapter):
    """
    Adapter for scraping jobs from Bundesagentur für Arbeit (arbeitsagentur.de).
    """

    SITE_NAME = "arbeitsagentur"
    BASE_URL = "https://www.arbeitsagentur.de"
    API_URL = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/jobs"

    def scrape(
        self,
        search_term: str | None = None,
        location: str | None = None,
        distance: int | None = 50,
        results_wanted: int = 15,
        hours_old: int | None = None,
    ) -> pd.DataFrame:
        
        jobs: list[dict[str, Any]] = []
        
        # We attempt to use their public REST API if possible
        query_params = {
            "size": results_wanted,
        }
        if search_term:
            query_params["was"] = search_term
        if location:
            query_params["wo"] = location
            if distance:
                query_params["umkreis"] = distance

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
            "X-API-Key": "jobboerse-jobsuche-pc" # A known public header for this API
        }

        try:
            with httpx.Client(timeout=15.0) as client:
                response = client.get(self.API_URL, params=query_params, headers=headers)
                
                # If API works, parse JSON. If not, fallback to empty or HTML scraping.
                if response.status_code == 200:
                    data = response.json()
                    stellenangebote = data.get("stellenangebote", [])
                    
                    for job in stellenangebote:
                        if len(jobs) >= results_wanted:
                            break
                            
                        ref_nr = job.get("refnr", "")
                        job_url = f"{self.BASE_URL}/jobsuche/suche?angebotsinfo=1&refnr={ref_nr}" if ref_nr else ""
                        
                        jobs.append({
                            "title": job.get("titel", "Unknown Title"),
                            "company": job.get("arbeitgeber", "Unknown Company"),
                            "location": job.get("arbeitsort", {}).get("ort", location or "Germany"),
                            "date_posted": job.get("veroeffentlichungsdatum"),
                            "job_url": job_url,
                            "site": self.SITE_NAME,
                            "job_type": job.get("arbeitszeitmodelle", [""])[0] if job.get("arbeitszeitmodelle") else None,
                        })
                else:
                    print(f"Arbeitsagentur API returned {response.status_code}. Fallback HTML parsing not implemented.")
                    
        except Exception as e:
            print(f"Error scraping Arbeitsagentur: {e}")

        return pd.DataFrame(jobs)
