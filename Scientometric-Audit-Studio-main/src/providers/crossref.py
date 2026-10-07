"""
Crossref REST API client with thread-safe rate limiting, exponential backoff, and polite pool compliance.
"""
import time
import logging
import urllib.parse
from typing import Optional, Dict, Any, List
import requests

from config import CROSSREF_MAILTO, USER_AGENT, REQUEST_TIMEOUT, MAX_RETRIES
from src.providers.cache_manager import CacheManager
from src.providers.rate_limiter import PoliteRateLimiter
from src.parsing.doi_extractor import normalize_doi

logger = logging.getLogger(__name__)


class CrossrefClient:
    """
    Client for querying Crossref metadata and bibliographic search.
    Protected by a global thread-safe rate limiter and 429 backoff coordinator.
    """
    BASE_URL = "https://api.crossref.org"
    _limiter = PoliteRateLimiter("Crossref", min_interval_seconds=0.35, default_backoff_seconds=6.0)

    def __init__(self, mailto: str = CROSSREF_MAILTO):
        self.mailto = mailto
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        })
        self.cache = CacheManager.get_instance()

    def is_available(self) -> bool:
        """Returns False if currently in a 429 cooldown window."""
        return not self._limiter.is_in_backoff()

    def get_by_doi(self, doi: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves work metadata by DOI. Cached locally.
        """
        norm_doi = normalize_doi(doi)
        if not norm_doi:
            return None

        # Check cache
        cached = self.cache.get("crossref_doi", norm_doi)
        if cached is not None:
            return cached

        url = f"{self.BASE_URL}/works/{urllib.parse.quote(norm_doi)}"
        data = self._request_with_retry(url)
        if data and "message" in data:
            work = self._extract_metadata(data["message"])
            self.cache.set("crossref_doi", norm_doi, work)
            return work

        # Cache negative result (404/not found)
        self.cache.set("crossref_doi", norm_doi, {}, status_code=404)
        return None

    def get_work_details(self, doi: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves full publication details and reference list directly from Crossref works endpoint.
        Cached under namespace 'crossref_work_details'.
        """
        norm_doi = normalize_doi(doi)
        if not norm_doi:
            return None

        cached = self.cache.get("crossref_work_details", norm_doi)
        if cached is not None:
            return cached

        url = f"{self.BASE_URL}/works/{urllib.parse.quote(norm_doi)}"
        data = self._request_with_retry(url)
        if data and "message" in data:
            msg = data["message"]
            self.cache.set("crossref_work_details", norm_doi, msg)
            return msg

        self.cache.set("crossref_work_details", norm_doi, {}, status_code=404)
        return None

    def get_work_references(self, doi: str) -> List[Dict[str, Any]]:
        """
        Extracts authoritative publisher-deposited references from Crossref.
        Returns a list of structured reference dictionaries.
        """
        work = self.get_work_details(doi)
        if not work:
            return []

        raw_refs = work.get("reference", [])
        parsed_refs = []
        for idx, r in enumerate(raw_refs, start=1):
            ref_doi = normalize_doi(r.get("DOI")) or ""
            ref_title = r.get("article-title") or r.get("volume-title") or r.get("series-title") or ""
            ref_author = r.get("author") or ""
            ref_year = None
            yr_str = str(r.get("year") or "").strip()
            if yr_str and yr_str[:4].isdigit():
                ref_year = int(yr_str[:4])

            parsed_refs.append({
                "reference_no": idx,
                "doi": ref_doi,
                "title": ref_title,
                "authors": ref_author,
                "year": ref_year,
                "journal": r.get("journal-title") or "",
                "volume": str(r.get("volume") or ""),
                "issue": str(r.get("issue") or ""),
                "pages": str(r.get("first-page") or ""),
                "raw_reference": r.get("unstructured") or "",
                "key": r.get("key") or "",
                "doi_asserted_by": r.get("doi-asserted-by") or "",
                "provider": "crossref",
            })
        return parsed_refs

    def search_bibliographic(self, query: str, rows: int = 3) -> List[Dict[str, Any]]:
        """
        Searches Crossref by bibliographic query string (e.g. title + author). Cached locally.
        """
        clean_query = query.strip()
        if not clean_query:
            return []

        cache_key = f"all_title_records_v2__{clean_query}__rows_{rows}"
        cached = self.cache.get("crossref_search", cache_key)
        if cached is not None:
            return cached.get("items", [])

        encoded_query = urllib.parse.quote_plus(clean_query)
        url = f"{self.BASE_URL}/works?query.bibliographic={encoded_query}&rows={rows}"
        
        data = self._request_with_retry(url)
        candidates = []
        if data and "message" in data and "items" in data["message"]:
            for item in data["message"]["items"]:
                meta = self._extract_metadata(item)
                if meta.get("title"):
                    candidates.append(meta)

        # Always cache search results, even if empty, to prevent re-querying
        self.cache.set("crossref_search", cache_key, {"items": candidates})
        return candidates

    def _request_with_retry(self, url: str) -> Optional[Dict[str, Any]]:
        for attempt in range(1, MAX_RETRIES + 1):
            # 1. Pacing & backoff enforcement across all threads
            self._limiter.acquire()
            
            try:
                resp = self.session.get(url, timeout=REQUEST_TIMEOUT)
                if resp.status_code == 200:
                    return resp.json()
                elif resp.status_code == 404:
                    return None
                elif resp.status_code == 429:
                    # HTTP 429 Too Many Requests -> Trigger coordinated backoff
                    retry_header = resp.headers.get("Retry-After")
                    wait = self._limiter.trigger_backoff(retry_header, attempt=attempt)
                    time.sleep(wait)
                elif resp.status_code in (500, 502, 503, 504):
                    wait = 3.0 * attempt
                    logger.warning(f"Crossref HTTP {resp.status_code}. Retrying in {wait:.1f}s...")
                    time.sleep(wait)
                else:
                    logger.warning(f"Crossref HTTP {resp.status_code} for {url}")
                    return None
            except requests.RequestException as e:
                wait = 2.0 * attempt
                logger.warning(f"Crossref request error: {e}. Attempt {attempt}/{MAX_RETRIES}.")
                time.sleep(wait)
        return None

    @staticmethod
    def _extract_metadata(item: Dict[str, Any]) -> Dict[str, Any]:
        """Converts raw Crossref item into normalized metadata dictionary."""
        titles = item.get("title", [])
        title = titles[0] if titles else ""
        
        authors_list = []
        for a in item.get("author", []):
            family = a.get("family", "")
            given = a.get("given", "")
            if family:
                authors_list.append(f"{family}, {given}".strip().rstrip(","))
        authors_str = "; ".join(authors_list)

        containers = item.get("container-title", [])
        journal = containers[0] if containers else ""

        year = None
        published = item.get("published-print") or item.get("published-online") or item.get("created")
        if published and "date-parts" in published and published["date-parts"]:
            dp = published["date-parts"][0]
            if dp and len(dp) >= 1 and isinstance(dp[0], int):
                year = dp[0]

        doi = normalize_doi(item.get("DOI", "")) or ""

        is_retracted = False
        update_to = item.get("update-to") or []
        for u in update_to:
            if u.get("type", "").lower() in ("retraction", "removal"):
                is_retracted = True

        return {
            "doi": doi,
            "title": title,
            "authors": authors_str,
            "journal": journal,
            "year": year,
            "volume": str(item.get("volume", "")),
            "issue": str(item.get("issue", "")),
            "pages": str(item.get("page", "")),
            "is_retracted": is_retracted,
            "provider": "crossref",
        }
