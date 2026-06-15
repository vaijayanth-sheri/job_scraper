import urllib.parse
from typing import Any
import pandas as pd
import httpx
from bs4 import BeautifulSoup

from job_search.adapters.base import JobAdapter


class EnglishJobsAdapter(JobAdapter):
    """
    Adapter for scraping jobs from EnglishJobs.de.
    """

    SITE_NAME = "englishjobs"
    BASE_URL = "https://englishjobs.de"

    def scrape(
        self,
        search_term: str | None = None,
        location: str | None = None,
        distance: int | None = 50,
        results_wanted: int = 15,
        hours_old: int | None = None,
    ) -> pd.DataFrame:
        
        jobs: list[dict[str, Any]] = []
        
        query_params = {}
        if search_term:
            query_params["q"] = search_term
        if location:
            query_params["l"] = location

        search_url = f"{self.BASE_URL}/jobs?" + urllib.parse.urlencode(query_params)

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

        try:
            with httpx.Client(timeout=15.0) as client:
                response = client.get(search_url, headers=headers)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.text, "html.parser")
                job_cards = soup.select(".job, .listing, article")
                
                for card in job_cards:
                    if len(jobs) >= results_wanted:
                        break
                        
                    title_elem = card.select_one("h2, h3, .title")
                    company_elem = card.select_one(".company, .employer")
                    location_elem = card.select_one(".location, .city")
                    link_elem = card.select_one("a")
                    
                    if not title_elem:
                        continue
                        
                    title = title_elem.get_text(strip=True)
                    company = company_elem.get_text(strip=True) if company_elem else "Unknown"
                    loc = location_elem.get_text(strip=True) if location_elem else location or "Germany"
                    
                    job_url = ""
                    if link_elem and link_elem.has_attr("href"):
                        href = link_elem["href"]
                        if href.startswith("http"):
                            job_url = href
                        else:
                            job_url = self.BASE_URL + (href if href.startswith("/") else f"/{href}")

                    jobs.append({
                        "title": title,
                        "company": company,
                        "location": loc,
                        "date_posted": None,
                        "job_url": job_url,
                        "site": self.SITE_NAME,
                        "job_type": None,
                    })

        except Exception as e:
            print(f"Error scraping EnglishJobs.de: {e}")

        return pd.DataFrame(jobs)
