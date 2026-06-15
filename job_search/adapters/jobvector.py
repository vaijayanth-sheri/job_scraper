import urllib.parse
from typing import Any
import pandas as pd
import httpx
from bs4 import BeautifulSoup

from job_search.adapters.base import JobAdapter


class JobvectorAdapter(JobAdapter):
    """
    Adapter for scraping jobs from Jobvector (jobvector.de).
    """

    SITE_NAME = "jobvector"
    BASE_URL = "https://www.jobvector.de"

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
            if distance:
                query_params["r"] = distance

        search_url = f"{self.BASE_URL}/jobsearch/?" + urllib.parse.urlencode(query_params)

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        try:
            with httpx.Client(timeout=15.0) as client:
                response = client.get(search_url, headers=headers)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.text, "html.parser")
                
                # Jobvector usually lists jobs in elements with class 'job-element' or similar.
                # Note: This is a best-effort structural parse. In a production app, 
                # these selectors would need constant maintenance.
                job_cards = soup.select(".job-list-item, .job-element, article.job")
                
                for card in job_cards:
                    if len(jobs) >= results_wanted:
                        break
                        
                    title_elem = card.select_one(".job-title, h2, h3")
                    company_elem = card.select_one(".company-name, .employer")
                    location_elem = card.select_one(".location, .city")
                    link_elem = card.select_one("a.job-link, a")
                    
                    title = title_elem.get_text(strip=True) if title_elem else "Unknown Title"
                    company = company_elem.get_text(strip=True) if company_elem else "Unknown Company"
                    loc = location_elem.get_text(strip=True) if location_elem else location or "Germany"
                    
                    job_url = ""
                    if link_elem and link_elem.has_attr("href"):
                        href = link_elem["href"]
                        if href.startswith("http"):
                            job_url = href
                        else:
                            job_url = self.BASE_URL + href

                    # Extract date if possible, else leave pd.NA or None
                    date_elem = card.select_one(".date, .posted-on")
                    date_posted = date_elem.get_text(strip=True) if date_elem else None
                    
                    jobs.append({
                        "title": title,
                        "company": company,
                        "location": loc,
                        "date_posted": date_posted,
                        "job_url": job_url,
                        "site": self.SITE_NAME,
                        "job_type": None,
                    })

        except Exception as e:
            print(f"Error scraping Jobvector: {e}")

        return pd.DataFrame(jobs)
