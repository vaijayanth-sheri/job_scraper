import pandas as pd
from typing import Any

# Fallback in case jobspy is not installed or has issues.
# In a real environment, it should be installed.
try:
    from jobspy import scrape_jobs as jobspy_scrape_jobs
except ImportError:
    def jobspy_scrape_jobs(*args, **kwargs):
        print("Warning: python-jobspy is not installed.")
        return pd.DataFrame()

from .jobvector import JobvectorAdapter
from .arbeitsagentur import ArbeitsagenturAdapter
from .englishjobs import EnglishJobsAdapter
from .devjobs import DevJobsAdapter

CUSTOM_ADAPTERS = {
    "jobvector": JobvectorAdapter(),
    "arbeitsagentur": ArbeitsagenturAdapter(),
    "englishjobs": EnglishJobsAdapter(),
    "devjobs": DevJobsAdapter(),
}

def scrape_jobs(
    site_name: str | list[str] | None = None,
    search_term: str | None = None,
    location: str | None = None,
    distance: int | None = 50,
    is_remote: bool = False,
    job_type: str | None = None,
    easy_apply: bool | None = None,
    results_wanted: int = 15,
    country_indeed: str = "usa",
    hyperlinks: bool = False,
    proxies: list[str] | str | None = None,
    ca_cert: str | None = None,
    offset: int | None = 0,
    hours_old: int | None = None,
    verbose: int = 2,
    **kwargs: Any,
) -> pd.DataFrame:
    """
    Wrapper around JobSpy's scrape_jobs that also routes to our custom German adapters.
    """
    if isinstance(site_name, str):
        site_name = [site_name]
    elif not site_name:
        site_name = ["linkedin", "indeed"]

    native_sites = []
    custom_sites = []

    for site in site_name:
        site_lower = site.lower()
        if site_lower in CUSTOM_ADAPTERS:
            custom_sites.append(site_lower)
        else:
            native_sites.append(site_lower)

    dfs = []

    # 1. Run native jobspy sites
    if native_sites:
        try:
            native_df = jobspy_scrape_jobs(
                site_name=native_sites,
                search_term=search_term,
                location=location,
                distance=distance,
                is_remote=is_remote,
                job_type=job_type,
                easy_apply=easy_apply,
                results_wanted=results_wanted,
                country_indeed=country_indeed,
                hyperlinks=hyperlinks,
                proxies=proxies,
                ca_cert=ca_cert,
                offset=offset,
                hours_old=hours_old,
                verbose=verbose,
                **kwargs,
            )
            if native_df is not None and not native_df.empty:
                dfs.append(native_df)
        except Exception as e:
            if verbose > 0:
                print(f"Error running native JobSpy: {e}")

    # 2. Run custom adapters
    for site in custom_sites:
        adapter = CUSTOM_ADAPTERS[site]
        try:
            custom_df = adapter.scrape(
                search_term=search_term,
                location=location,
                distance=distance,
                results_wanted=results_wanted,
                hours_old=hours_old,
            )
            if custom_df is not None and not custom_df.empty:
                dfs.append(custom_df)
        except Exception as e:
            if verbose > 0:
                print(f"Error running adapter for {site}: {e}")

    if not dfs:
        return pd.DataFrame()
    
    return pd.concat(dfs, ignore_index=True)
