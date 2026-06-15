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
            "X-API-Key": "jobboerse-jobsuche-pc"
        }

        try:
            with httpx.Client(timeout=15.0, follow_redirects=True) as client:
                # Try the API
                response = client.get(self.API_URL, params=query_params, headers=headers)
                
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
                    # 403 Fallback: Scrape the HTML directly
                    html_params = {}
                    if search_term:
                        html_params["was"] = search_term
                    if location:
                        html_params["wo"] = location
                        if distance:
                            html_params["umkreis"] = distance

                    search_url = f"{self.BASE_URL}/jobsuche/suche?" + urllib.parse.urlencode(html_params)
                    
                    html_headers = {
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                        "Accept": "text/html,application/xhtml+xml",
                        "Accept-Language": "de-DE,de;q=0.9",
                    }
                    html_res = client.get(search_url, headers=html_headers)
                    html_res.raise_for_status()
                    
                    soup = BeautifulSoup(html_res.text, "html.parser")
                    job_cards = soup.select(".ergebnisliste-item, li[data-test='ergebnis-liste-element']")
                    
                    for card in job_cards:
                        if len(jobs) >= results_wanted:
                            break
                        
                        title_elem = card.select_one("a[data-test='job-titel'], h2")
                        company_elem = card.select_one("[data-test='arbeitgeber']")
                        location_elem = card.select_one("[data-test='arbeitsort']")
                        
                        if not title_elem:
                            continue
                            
                        title = title_elem.get_text(strip=True)
                        company = company_elem.get_text(strip=True) if company_elem else "Unknown Company"
                        loc = location_elem.get_text(strip=True) if location_elem else location or "Germany"
                        
                        job_url = ""
                        if title_elem.has_attr("href"):
                            href = title_elem["href"]
                            if href.startswith("http"):
                                job_url = href
                            else:
                                job_url = self.BASE_URL + "/jobsuche/" + href.lstrip("/")

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
            print(f"Error scraping Arbeitsagentur: {e}")

        return pd.DataFrame(jobs)
