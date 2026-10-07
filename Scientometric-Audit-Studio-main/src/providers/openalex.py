"""
OpenAlex REST API client with thread-safe rate limiting, caching, and polite pool identification.
"""
import time
import logging
import re
import urllib.parse
from typing import Optional, Dict, Any, List
import requests

from config import OPENALEX_EMAIL, USER_AGENT, REQUEST_TIMEOUT, MAX_RETRIES
from src.providers.cache_manager import CacheManager
from src.providers.rate_limiter import PoliteRateLimiter
from src.parsing.doi_extractor import normalize_doi

logger = logging.getLogger(__name__)


class OpenAlexClient:
    """
    Client for querying OpenAlex works metadata and search.
    Protected by a global thread-safe rate limiter and 429 backoff coordinator.
    """
    BASE_URL = "https://api.openalex.org"
    _limiter = PoliteRateLimiter("OpenAlex", min_interval_seconds=0.40, default_backoff_seconds=6.0)

    def __init__(self, email: str = OPENALEX_EMAIL):
        self.email = email
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        })
        self.cache = CacheManager.get_instance()
        self._quota_unavailable_until = 0.0

    def is_available(self) -> bool:
        """Returns False if currently cooling down from a 429."""
        return (
            time.time() >= self._quota_unavailable_until
            and not self._limiter.is_in_backoff()
        )

    def get_by_doi(self, doi: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves work metadata by DOI. Cached locally.
        """
        norm_doi = normalize_doi(doi)
        if not norm_doi:
            return None

        # Check cache
        cached = self.cache.get("openalex_doi", norm_doi)
        if cached is not None:
            return cached

        url = f"{self.BASE_URL}/works/https://doi.org/{urllib.parse.quote(norm_doi)}"
        data = self._request_with_retry(url)
        if data and "id" in data:
            work = self._extract_metadata(data)
            self.cache.set("openalex_doi", norm_doi, work)
            return work

        self.cache.set("openalex_doi", norm_doi, {}, status_code=404)
        return None

    def search_by_title(self, title: str, rows: int = 3) -> List[Dict[str, Any]]:
        """
        Searches OpenAlex by title string. Cached locally.
        """
        clean_title = title.strip()
        if not clean_title or len(clean_title) < 5:
            return []

        cache_key = f"all_title_records_v5__{clean_title}__rows_{rows}"
        cached = self.cache.get("openalex_search", cache_key)
        if cached is not None:
            return cached.get("items", [])

        # OpenAlex filter syntax rejects punctuation such as commas and treats
        # '?' and '*' specially. Search the title-only index after replacing
        # punctuation with spaces; this remains precise and supports real
        # publication titles containing those characters.
        searchable_title = " ".join(re.sub(r"[^\w\s]", " ", clean_title).split())
        encoded_title = urllib.parse.quote_plus(searchable_title)
        url = f"{self.BASE_URL}/works?filter=title.search:{encoded_title}&per_page={rows}"
        
        data = self._request_with_retry(url)
        candidates = []
        if data and "results" in data:
            for item in data["results"]:
                meta = self._extract_metadata(item)
                if meta.get("title"):
                    candidates.append(meta)

        # Always cache search result to prevent re-querying
        self.cache.set("openalex_search", cache_key, {"items": candidates})
        return candidates

    def _request_with_retry(self, url: str) -> Optional[Dict[str, Any]]:
        for attempt in range(1, MAX_RETRIES + 1):
            if time.time() < self._quota_unavailable_until:
                return None
            self._limiter.acquire()
            if time.time() < self._quota_unavailable_until:
                return None
            try:
                resp = self.session.get(url, timeout=REQUEST_TIMEOUT)
                if resp.status_code == 200:
                    return resp.json()
                elif resp.status_code == 404:
                    return None
                elif resp.status_code == 429:
                    retry_header = resp.headers.get("Retry-After")
                    if retry_header and retry_header.strip().isdigit() and int(retry_header) > 60:
                        self._quota_unavailable_until = time.time() + min(
                            int(retry_header), 3600
                        )
                        logger.warning(
                            "OpenAlex quota window is unavailable; continuing with other registries."
                        )
                        return None
                    wait = self._limiter.trigger_backoff(retry_header, attempt=attempt)
                    time.sleep(wait)
                elif resp.status_code in (500, 502, 503, 504):
                    wait = 3.0 * attempt
                    logger.warning(f"OpenAlex HTTP {resp.status_code}. Retrying in {wait:.1f}s...")
                    time.sleep(wait)
                else:
                    logger.warning(f"OpenAlex HTTP {resp.status_code} for {url}")
                    return None
            except requests.RequestException as e:
                wait = 2.0 * attempt
                logger.warning(f"OpenAlex request error: {e}. Attempt {attempt}/{MAX_RETRIES}.")
                time.sleep(wait)
        return None

    @staticmethod
    def _extract_metadata(item: Dict[str, Any]) -> Dict[str, Any]:
        """Converts raw OpenAlex item into normalized metadata dictionary."""
        doi_raw = item.get("doi") or ""
        doi = normalize_doi(doi_raw) or ""

        # Title
        title = item.get("display_name") or item.get("title") or ""

        # Authors
        authors_list = []
        for authorship in item.get("authorships", []):
            author_obj = authorship.get("author", {})
            name = author_obj.get("display_name", "")
            if name:
                authors_list.append(name)
        authors_str = "; ".join(authors_list)

        # Journal / Venue
        journal = ""
        primary_loc = item.get("primary_location") or {}
        source = primary_loc.get("source") or {}
        if source:
            journal = source.get("display_name", "")

        # Biblio
        biblio = item.get("biblio") or {}
        volume = str(biblio.get("volume") or "")
        issue = str(biblio.get("issue") or "")
        first_page = biblio.get("first_page") or ""
        last_page = biblio.get("last_page") or ""
        pages = f"{first_page}-{last_page}".strip("-") if (first_page or last_page) else ""

        # Year
        year = item.get("publication_year")

        # Retracted status
        is_retracted = item.get("is_retracted", False)

        return {
            "doi": doi,
            "title": title,
            "authors": authors_str,
            "journal": journal,
            "year": year,
            "volume": volume,
            "issue": issue,
            "pages": pages,
            "is_retracted": is_retracted,
            "provider": "openalex",
        }
