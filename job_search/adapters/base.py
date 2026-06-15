from abc import ABC, abstractmethod
import pandas as pd


class JobAdapter(ABC):
    """
    Abstract base class for custom job scrapers.
    Follows the input/output pattern expected by JobSpy.
    """

    @abstractmethod
    def scrape(
        self,
        search_term: str | None = None,
        location: str | None = None,
        distance: int | None = 50,
        results_wanted: int = 15,
        hours_old: int | None = None,
    ) -> pd.DataFrame:
        """
        Scrape jobs from the target site.

        Returns a Pandas DataFrame containing the following columns:
        - title
        - company
        - location
        - date_posted
        - job_url
        - site
        - job_type
        """
        pass
