"""
DOI resolution engine. Follows HTTP redirects from doi.org, tracks destination URLs,
and measures response latency.
"""
import time
import logging
from typing import Dict, Any, Optional
import requests

from config import REQUEST_TIMEOUT, USER_AGENT
from src.providers.cache_manager import CacheManager
from src.parsing.doi_extractor import normalize_doi

logger = logging.getLogger(__name__)


class DOIResolver:
    """
    Resolves DOIs via https://doi.org and checks web accessibility.
    """
    RESOLVER_URL = "https://doi.org"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })
        self.cache = CacheManager.get_instance()

    def resolve(self, doi: str) -> Dict[str, Any]:
        """
        Resolves a DOI and returns resolution diagnostics. Cached locally.
        """
        norm_doi = normalize_doi(doi)
        if not norm_doi:
            return {
                "doi_exists": False,
                "doi_resolves": False,
                "http_status": None,
                "final_url": "",
                "redirect_count": 0,
                "response_time_ms": 0.0,
                "error": "INVALID_DOI_SYNTAX",
            }

        cached = self.cache.get("doi_resolution", norm_doi)
        if cached is not None:
            return cached

        target_url = f"{self.RESOLVER_URL}/{norm_doi}"
        start_time = time.time()
        
        try:
            # Use HEAD first or GET with stream=True to avoid downloading large bodies
            resp = self.session.get(target_url, timeout=REQUEST_TIMEOUT, allow_redirects=True, stream=True)
            elapsed_ms = round((time.time() - start_time) * 1000, 2)
            
            status = resp.status_code
            final_url = str(resp.url)
            redirect_count = len(resp.history)
            
            # Close stream
            resp.close()

            # Interpret status
            # If doi.org gave 404, DOI does not exist
            # If redirected to publisher and got 200, DOI exists and resolves
            # If redirected to publisher and got 403, DOI exists, resolves, but access is restricted
            doi_exists = status != 404
            doi_resolves = status in (200, 301, 302, 303, 307, 308, 401, 403)

            result = {
                "doi_exists": doi_exists,
                "doi_resolves": doi_resolves,
                "http_status": status,
                "final_url": final_url,
                "redirect_count": redirect_count,
                "response_time_ms": elapsed_ms,
                "error": None,
            }

        except requests.Timeout:
            elapsed_ms = round((time.time() - start_time) * 1000, 2)
            result = {
                "doi_exists": False,
                "doi_resolves": False,
                "http_status": None,
                "final_url": target_url,
                "redirect_count": 0,
                "response_time_ms": elapsed_ms,
                "error": "TIMEOUT",
            }
        except requests.RequestException as e:
            elapsed_ms = round((time.time() - start_time) * 1000, 2)
            result = {
                "doi_exists": False,
                "doi_resolves": False,
                "http_status": None,
                "final_url": target_url,
                "redirect_count": 0,
                "response_time_ms": elapsed_ms,
                "error": str(e),
            }

        self.cache.set("doi_resolution", norm_doi, result, status_code=result.get("http_status") or 0)
        return result

