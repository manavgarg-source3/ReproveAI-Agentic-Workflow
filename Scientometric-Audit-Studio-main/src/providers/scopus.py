"""
Elsevier Scopus Search API client with caching, quota monitoring, and polite retry.
"""
import time
import re
import logging
import urllib.parse
from typing import Optional, Dict, Any, List
import requests

from config import ELSEVIER_API_KEY, REQUEST_TIMEOUT, MAX_RETRIES, BACKOFF_FACTOR
from src.providers.cache_manager import CacheManager
from src.parsing.doi_extractor import normalize_doi

logger = logging.getLogger(__name__)


class ScopusClient:
    """
    Client for querying Elsevier Scopus Search API.
    """
    BASE_URL = "https://api.elsevier.com/content/search/scopus"

    def __init__(self, api_key: str = ELSEVIER_API_KEY):
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "X-ELS-APIKey": self.api_key,
        })
        self.cache = CacheManager.get_instance()
        self.rate_limit_remaining: Optional[int] = None

    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_key != "your_elsevier_api_key_here")

    def is_available(self) -> bool:
        """Returns False if Scopus API key has 0 remaining quota or is in rate limit cooldown."""
        if not self.is_configured():
            return False
        if self.rate_limit_remaining == 0:
            return False
        if getattr(self, "_rate_limited_until", 0) > time.time():
            return False
        return True

    def get_by_doi(self, doi: str) -> Optional[Dict[str, Any]]:
        """
        Queries Scopus by DOI. Cached locally.
        """
        if not self.is_configured():
            return None

        norm_doi = normalize_doi(doi)
        if not norm_doi:
            return None

        cached = self.cache.get("scopus_doi", norm_doi)
        if cached is not None:
            return cached

        query = f'DOI("{norm_doi}")'
        items = self._search(query, count=1)
        if items:
            work = items[0]
            self.cache.set("scopus_doi", norm_doi, work)
            return work

        self.cache.set("scopus_doi", norm_doi, {}, status_code=404)
        return None

    def search_by_title_and_author(self, title: str, author: str = "", count: int = 3) -> List[Dict[str, Any]]:
        """
        Searches Scopus by title and optional author. Cached locally.
        """
        if not self.is_configured() or not title:
            return []

        clean_title = title.replace('"', "").strip()
        if len(clean_title) < 5:
            return []

        if author:
            first_author = author.split(";")[0].strip()
            if "," in first_author:
                clean_author = first_author.split(",", 1)[0].strip()
            else:
                clean_author = first_author.split()[-1].strip()
            query = f'TITLE("{clean_title[:100]}") AND AUTH("{clean_author}")'
        else:
            query = f'TITLE("{clean_title[:100]}")'

        cache_key = f"v2__{query}__count_{count}"
        cached = self.cache.get("scopus_search", cache_key)
        if cached is not None:
            return cached.get("items", [])

        items = self._search(query, count=count)
        self.cache.set("scopus_search", cache_key, {"items": items})
        return items

    def _search(self, query: str, count: int = 3) -> List[Dict[str, Any]]:
        # Fast circuit-breaker: if Scopus API returned 429 recently, skip search until cooldown expires
        if getattr(self, "_rate_limited_until", 0) > time.time():
            return []

        encoded_query = urllib.parse.quote_plus(query)
        url = f"{self.BASE_URL}?query={encoded_query}&count={count}"
        
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = self.session.get(url, timeout=REQUEST_TIMEOUT)
                # Track quota
                rem = resp.headers.get("X-RateLimit-Remaining")
                if rem and rem.isdigit():
                    self.rate_limit_remaining = int(rem)

                if resp.status_code == 200:
                    data = resp.json()
                    search_res = data.get("search-results", {})
                    entries = search_res.get("entry", [])
                    results = []
                    for entry in entries:
                        if "@error" in entry:
                            continue
                        meta = self._extract_metadata(entry)
                        if meta.get("doi") or meta.get("title"):
                            results.append(meta)
                    return results
                elif resp.status_code == 404:
                    return []
                elif resp.status_code == 429:
                    self.rate_limit_remaining = 0
                    reset_header = resp.headers.get("X-RateLimit-Reset")
                    reset_wait = (int(reset_header) - time.time()) if (reset_header and reset_header.isdigit()) else 300
                    logger.warning(f"Scopus HTTP 429 rate limit received. Cooling down Scopus for {max(60, int(reset_wait))}s.")
                    self._rate_limited_until = time.time() + max(60, int(reset_wait))
                    return []
                elif resp.status_code in (500, 502, 503, 504):
                    wait = BACKOFF_FACTOR ** attempt
                    logger.warning(f"Scopus HTTP {resp.status_code}. Retrying in {wait:.1f}s...")
                    time.sleep(wait)
                else:
                    logger.warning(f"Scopus HTTP {resp.status_code} for query: {query}")
                    return []
            except requests.RequestException as e:
                wait = BACKOFF_FACTOR ** attempt
                logger.warning(f"Scopus request error: {e}. Attempt {attempt}/{MAX_RETRIES}.")
                time.sleep(wait)
        return []

    @staticmethod
    def _extract_metadata(entry: Dict[str, Any]) -> Dict[str, Any]:
        """Converts Scopus search entry to normalized metadata."""
        doi_raw = ScopusClient._extract_text(entry.get("prism:doi"))
        doi = normalize_doi(doi_raw) or ""

        title = ScopusClient._extract_text(entry.get("dc:title"))
        authors = ScopusClient._extract_text(entry.get("dc:creator"))
        journal = ScopusClient._extract_text(entry.get("prism:publicationName"))
        
        # Cover date e.g. "2021-12-01"
        year = None
        date_str = entry.get("prism:coverDate") or ""
        if date_str and len(date_str) >= 4 and date_str[:4].isdigit():
            year = int(date_str[:4])

        volume = str(entry.get("prism:volume") or "")
        issue = str(entry.get("prism:issueIdentifier") or "")
        pages = str(entry.get("prism:pageRange") or "")
        eid = str(entry.get("eid") or "")

        return {
            "eid": eid,
            "doi": doi,
            "title": title,
            "authors": authors,
            "journal": journal,
            "year": year,
            "volume": volume,
            "issue": issue,
            "pages": pages,
            "is_retracted": False,
            "provider": "scopus",
        }

    def get_eid_by_doi(self, doi: str) -> Optional[str]:
        """Looks up Scopus EID for a given DOI.
        First tries the Search API (get_by_doi), then falls back to the
        Abstract Retrieval API by DOI which uses a separate rate limit pool.
        """
        item = self.get_by_doi(doi)
        if item and item.get("eid"):
            return item["eid"]

        # Fallback: use Abstract Retrieval API by DOI (separate rate limit pool)
        if self.is_configured() and doi:
            try:
                norm_doi = normalize_doi(doi) or doi
                url = f"https://api.elsevier.com/content/abstract/doi/{norm_doi}?view=META"
                resp = self.session.get(url, timeout=REQUEST_TIMEOUT)
                if resp.status_code == 200:
                    data = resp.json().get("abstracts-retrieval-response", {})
                    core = data.get("coredata", {})
                    eid = core.get("eid") or ""
                    if eid:
                        logger.info(f"Resolved DOI {doi} to Scopus EID {eid} via Abstract Retrieval API")
                        return eid
            except Exception as e:
                logger.warning(f"Abstract Retrieval EID lookup for DOI {doi} failed: {e}")
        return None

    def get_abstract_details_by_doi(self, doi: str, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Fetches complete document metadata and authoritative reference list using the
        Abstract Retrieval API endpoint by DOI (/content/abstract/doi/{doi}?view=FULL).

        This is critical when the Scopus Search API is rate-limited (HTTP 429) but
        the Abstract Retrieval API pool still has quota remaining — they use separate
        rate limit pools.

        Cached in SQLite under namespace 'scopus_abstract_refs' using the resolved EID.
        """
        empty_res = {
            "source_title": "",
            "source_authors": "",
            "source_year": None,
            "source_doi": "",
            "eid": "",
            "total_reported": 0,
            "references": [],
        }
        if not self.is_configured() or not doi:
            return empty_res

        norm_doi = normalize_doi(doi) or doi

        url_full = f"https://api.elsevier.com/content/abstract/doi/{norm_doi}?view=FULL"
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = self.session.get(url_full, timeout=REQUEST_TIMEOUT)
                rem = resp.headers.get("X-RateLimit-Remaining")
                if rem and rem.isdigit():
                    # Note: this is the Abstract Retrieval pool quota, not the Search pool
                    pass

                if resp.status_code == 200:
                    data = resp.json().get("abstracts-retrieval-response", {})
                    core = data.get("coredata", {})
                    resolved_eid = core.get("eid") or ""
                    source_title = ScopusClient._extract_text(core.get("dc:title"))
                    source_doi = normalize_doi(core.get("prism:doi")) or core.get("prism:doi") or ""

                    source_year = None
                    date_str = str(core.get("prism:coverDate") or "")
                    if len(date_str) >= 4 and date_str[:4].isdigit():
                        source_year = int(date_str[:4])

                    auth_list = data.get("authors", {}).get("author", [])
                    if isinstance(auth_list, dict):
                        auth_list = [auth_list]
                    auth_names = []
                    for a in auth_list:
                        if isinstance(a, dict):
                            n = a.get("ce:indexed-name") or a.get("ce:surname") or ""
                            if n:
                                auth_names.append(n)
                    source_authors = "; ".join(auth_names) if auth_names else ScopusClient._extract_text(core.get("dc:creator"))

                    bib = data.get("item", {}).get("bibrecord", {}).get("tail", {}).get("bibliography", {})
                    raw_refs = bib.get("reference", [])
                    if isinstance(raw_refs, dict):
                        raw_refs = [raw_refs]

                    parsed_refs = ScopusClient._parse_bibrecord_references(raw_refs) if raw_refs else []
                    result_payload = {
                        "source_title": source_title,
                        "source_authors": source_authors,
                        "source_year": source_year,
                        "source_doi": source_doi,
                        "eid": resolved_eid,
                        "total_reported": len(parsed_refs),
                        "references": parsed_refs,
                    }

                    # Cache under EID if available, so get_abstract_details(eid) also benefits
                    if resolved_eid:
                        clean_eid = resolved_eid if resolved_eid.startswith("2-s2.0-") else f"2-s2.0-{resolved_eid}"
                        self.cache.set("scopus_abstract_refs", clean_eid, result_payload)
                        logger.info(f"Retrieved {len(parsed_refs)} references for DOI {norm_doi} (EID {resolved_eid}) via Abstract Retrieval API")

                    return result_payload

                elif resp.status_code == 429:
                    logger.warning(f"Scopus Abstract Retrieval HTTP 429 for DOI {norm_doi}.")
                    break
                elif resp.status_code == 404:
                    logger.info(f"DOI {norm_doi} not found in Scopus Abstract Retrieval.")
                    break
                elif resp.status_code in (500, 502, 503, 504):
                    wait = BACKOFF_FACTOR ** attempt
                    time.sleep(wait)
                else:
                    break
            except requests.RequestException as e:
                wait = BACKOFF_FACTOR ** attempt
                logger.warning(f"Abstract Retrieval request error for DOI {norm_doi}: {e}")
                time.sleep(wait)

        return empty_res

    def get_abstract_details(self, eid: str, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Fetches complete document metadata and authoritative reference list directly from Scopus.
        Prefers view=FULL (which contains all bibliography references regardless of count without 40-ref pagination limits).
        Falls back to paginated view=REF if view=FULL bibliography is unavailable.
        Cached in SQLite under namespace 'scopus_abstract_refs'.
        """
        empty_res = {
            "source_title": "",
            "source_authors": "",
            "source_year": None,
            "source_doi": "",
            "total_reported": 0,
            "references": [],
        }
        if not self.is_configured() or not eid:
            return empty_res

        clean_eid = eid if eid.startswith("2-s2.0-") else f"2-s2.0-{eid}"

        if not force_refresh:
            cached = self.cache.get("scopus_abstract_refs", clean_eid)
            if cached is not None and "total_reported" in cached:
                total_reported = cached.get("total_reported") or 0
                refs = cached.get("references", [])
                has_corrupted_titles = any(r.get("title") == "{}" for r in refs)
                if not has_corrupted_titles and (len(refs) >= total_reported or len(refs) != 40):
                    return {
                        "source_title": cached.get("source_title", ""),
                        "source_authors": cached.get("source_authors", ""),
                        "source_year": cached.get("source_year"),
                        "source_doi": cached.get("source_doi", ""),
                        "total_reported": total_reported or len(refs),
                        "references": refs,
                    }

        # Step 1: Try view=FULL first (contains full bibliography in item.bibrecord.tail.bibliography.reference)
        url_full = f"https://api.elsevier.com/content/abstract/eid/{clean_eid}?view=FULL"
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = self.session.get(url_full, timeout=REQUEST_TIMEOUT)
                rem = resp.headers.get("X-RateLimit-Remaining")
                if rem and rem.isdigit():
                    self.rate_limit_remaining = int(rem)

                if resp.status_code == 200:
                    data = resp.json().get("abstracts-retrieval-response", {})
                    core = data.get("coredata", {})
                    source_title = ScopusClient._extract_text(core.get("dc:title"))
                    source_doi = normalize_doi(core.get("prism:doi")) or core.get("prism:doi") or ""

                    # Extract source year
                    source_year = None
                    date_str = str(core.get("prism:coverDate") or "")
                    if len(date_str) >= 4 and date_str[:4].isdigit():
                        source_year = int(date_str[:4])

                    # Extract source authors
                    auth_list = data.get("authors", {}).get("author", [])
                    if isinstance(auth_list, dict):
                        auth_list = [auth_list]
                    auth_names = []
                    for a in auth_list:
                        if isinstance(a, dict):
                            n = a.get("ce:indexed-name") or a.get("ce:surname") or ""
                            if n:
                                auth_names.append(n)
                    source_authors = "; ".join(auth_names) if auth_names else ScopusClient._extract_text(core.get("dc:creator"))

                    # Extract references from bibrecord
                    bib = data.get("item", {}).get("bibrecord", {}).get("tail", {}).get("bibliography", {})
                    raw_refs = bib.get("reference", [])
                    if isinstance(raw_refs, dict):
                        raw_refs = [raw_refs]

                    if raw_refs:
                        parsed_refs = ScopusClient._parse_bibrecord_references(raw_refs)
                        result_payload = {
                            "source_title": source_title,
                            "source_authors": source_authors,
                            "source_year": source_year,
                            "source_doi": source_doi,
                            "total_reported": len(parsed_refs),
                            "references": parsed_refs,
                        }
                        self.cache.set("scopus_abstract_refs", clean_eid, result_payload)
                        return result_payload

                elif resp.status_code == 429:
                    logger.warning(f"Scopus HTTP 429 rate limit received for EID {clean_eid}. Cooling down Scopus.")
                    self._rate_limited_until = time.time() + 300
                    break
                elif resp.status_code in (500, 502, 503, 504):
                    wait = BACKOFF_FACTOR ** attempt
                    time.sleep(wait)
                else:
                    break
            except requests.RequestException:
                wait = BACKOFF_FACTOR ** attempt
                time.sleep(wait)

        # Step 2: Fallback to view=REF with multi-page iteration
        url_ref = f"https://api.elsevier.com/content/abstract/eid/{clean_eid}?view=REF"
        all_raw_refs = []
        source_title = f"Scopus Publication ({clean_eid})"
        total_expected = 0

        current_url = url_ref
        while current_url and len(all_raw_refs) < 500:
            try:
                resp = self.session.get(current_url, timeout=REQUEST_TIMEOUT)
                if resp.status_code == 200:
                    ref_data = resp.json().get("abstracts-retrieval-response", {}).get("references", {})
                    total_expected = int(ref_data.get("@total-references") or 0)
                    page_refs = ref_data.get("reference", [])
                    if isinstance(page_refs, dict):
                        page_refs = [page_refs]
                    all_raw_refs.extend(page_refs)

                    if len(all_raw_refs) >= total_expected or not total_expected:
                        break

                    next_url = None
                    last_url = None
                    for l in ref_data.get("link", []):
                        if l.get("@ref") == "next":
                            next_url = l.get("@href")
                        elif l.get("@ref") == "last":
                            last_url = l.get("@href")

                    if next_url and total_expected and len(all_raw_refs) + 40 > total_expected:
                        current_url = last_url or next_url
                    else:
                        current_url = next_url
                else:
                    break
            except requests.RequestException:
                break

        unique_refs = {}
        for r in all_raw_refs:
            rid = str(r.get("@id") or len(unique_refs) + 1)
            unique_refs[rid] = r

        parsed_refs = self._parse_scopus_references(list(unique_refs.values()))
        result_payload = {
            "source_title": source_title,
            "source_authors": "",
            "source_year": None,
            "source_doi": "",
            "total_reported": total_expected or len(parsed_refs),
            "references": parsed_refs,
        }
        if parsed_refs:
            self.cache.set("scopus_abstract_refs", clean_eid, result_payload)
        return result_payload

    def get_abstract_references(self, eid: str, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """
        Fetches authoritative reference list directly from Scopus.
        """
        details = self.get_abstract_details(eid, force_refresh=force_refresh)
        return details.get("references", [])

    @staticmethod
    def _extract_text(val: Any) -> str:
        """Recursively extracts clean string content from string, dict, or list returned by Elsevier APIs."""
        if val is None:
            return ""
        if isinstance(val, str):
            return val.strip()
        if isinstance(val, list):
            for item in val:
                txt = ScopusClient._extract_text(item)
                if txt:
                    return txt
            return ""
        if isinstance(val, dict):
            for k in ("$", "value", "#text", "_"):
                if k in val and val[k]:
                    return ScopusClient._extract_text(val[k])
            for v in val.values():
                if isinstance(v, str) and v.strip():
                    return v.strip()
            return ""
        if isinstance(val, (int, float)):
            return str(val).strip()
        return ""

    @staticmethod
    def _parse_scopus_references(raw_refs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Parses Scopus API reference objects into standardized dictionaries."""
        results = []
        for r in raw_refs:
            rid_str = r.get("@id") or r.get("derivedSequence") or "0"
            ref_no = int(rid_str) if str(rid_str).isdigit() else len(results) + 1
            rtype = str(r.get("type") or "")
            scopus_id = str(r.get("scopus-id") or "")
            scopus_eid = str(r.get("scopus-eid") or "")
            is_linked = (rtype == "resolvedReference")

            doi_raw = ScopusClient._extract_text(r.get("ce:doi"))
            doi = normalize_doi(doi_raw) or ""

            title = ScopusClient._extract_text(r.get("title"))
            if title == "{}":
                title = ""
            journal = ScopusClient._extract_text(r.get("sourcetitle"))
            if journal == "{}":
                journal = ""
            if not title and journal:
                title = journal

            # Volume / Issue / Pages
            vol_info = r.get("volisspag") or {}
            volume = ""
            issue = ""
            pages = ""
            if isinstance(vol_info, dict):
                voliss = vol_info.get("voliss") or {}
                if isinstance(voliss, dict):
                    volume = str(voliss.get("@volume") or "")
                    issue = str(voliss.get("@issue") or "")
                pagerange = vol_info.get("pagerange") or {}
                if isinstance(pagerange, dict):
                    first = pagerange.get("@first") or ""
                    last = pagerange.get("@last") or ""
                    pages = f"{first}-{last}" if (first and last) else first

            # Year
            year = None
            date_str = r.get("prism:coverDate") or ""
            if date_str and len(date_str) >= 4 and date_str[:4].isdigit():
                year = int(date_str[:4])
            elif volume and volume.isdigit() and 1800 <= int(volume) <= 2030:
                year = int(volume)

            # Authors
            author_names = []
            author_list = r.get("author-list")
            if author_list and isinstance(author_list, dict):
                auths = author_list.get("author") or []
                if isinstance(auths, dict):
                    auths = [auths]
                for a in auths:
                    if isinstance(a, dict):
                        name = a.get("ce:indexed-name") or a.get("ce:surname") or ""
                        if name:
                            author_names.append(name)
            authors_str = "; ".join(author_names)

            scopus_link = (
                f"https://www.scopus.com/pages/publications/{scopus_id}?origin=resultslist"
                if (is_linked and scopus_id)
                else "Not linked in Scopus"
            )

            results.append({
                "reference_no": ref_no,
                "scopus_id": scopus_id,
                "scopus_eid": scopus_eid,
                "scopus_type": rtype,
                "scopus_linked": is_linked,
                "scopus_link": scopus_link,
                "doi": doi,
                "title": title,
                "journal": journal,
                "year": year,
                "volume": volume,
                "issue": issue,
                "pages": pages,
                "authors": authors_str,
                "raw_fulltext": str(r.get("ref-fulltext") or ""),
            })
        return results

    @staticmethod
    def _parse_bibrecord_references(raw_refs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Parses Scopus bibrecord reference objects into standardized dictionaries."""
        results = []
        for r in raw_refs:
            rid_str = r.get("@id") or "0"
            ref_no = int(rid_str) if str(rid_str).isdigit() else len(results) + 1
            info = r.get("ref-info") or {}

            # Extract Scopus ID and DOI from refd-itemidlist
            scopus_id = ""
            doi = ""
            itemid_list = info.get("refd-itemidlist", {}).get("itemid", [])
            if isinstance(itemid_list, dict):
                itemid_list = [itemid_list]
            for it in itemid_list:
                if isinstance(it, dict):
                    id_type = it.get("@idtype", "")
                    val = str(it.get("$") or "").strip()
                    if id_type == "SGR" and val:
                        scopus_id = val
                    elif id_type == "DOI" and val:
                        doi = normalize_doi(val) or val

            # Also check ce:doi if not found
            if not doi:
                doi_raw = ScopusClient._extract_text(info.get("ce:doi"))
                doi = normalize_doi(doi_raw) or ""

            is_linked = bool(scopus_id)
            scopus_eid = f"2-s2.0-{scopus_id}" if scopus_id else ""
            scopus_link = (
                f"https://www.scopus.com/pages/publications/{scopus_id}?origin=resultslist"
                if scopus_id else "Not linked in Scopus"
            )

            # Title
            title_info = info.get("ref-title")
            title = ""
            if isinstance(title_info, dict):
                title = ScopusClient._extract_text(title_info.get("ref-titletext") or title_info)
            elif isinstance(title_info, str):
                title = title_info.strip()

            if not title or title == "{}":
                title = ScopusClient._extract_text(info.get("title"))
            if title == "{}":
                title = ""

            # Journal
            # Journal / Sourcetitle
            journal = ScopusClient._extract_text(info.get("ref-sourcetitle") or info.get("sourcetitle"))
            if journal == "{}":
                journal = ""

            # In Scopus, books, reports, monographs, and whitepapers often do not have ref-title,
            # and their title is stored in ref-sourcetitle
            if not title and journal:
                title = journal

            # Year
            pub_year = info.get("ref-publicationyear") or {}
            year = None
            if isinstance(pub_year, dict):
                y_str = pub_year.get("@first") or ""
                if str(y_str).isdigit():
                    year = int(y_str)
            if not year:
                y_str = ScopusClient._extract_text(pub_year)
                if y_str and len(y_str) >= 4 and y_str[:4].isdigit():
                    year = int(y_str[:4])

            # Authors
            author_names = []
            authors_info = info.get("ref-authors") or {}
            auth_list = authors_info.get("author") or []
            if isinstance(auth_list, dict):
                auth_list = [auth_list]
            for a in auth_list:
                if isinstance(a, dict):
                    name = a.get("ce:indexed-name") or a.get("ce:surname") or ""
                    if name:
                        author_names.append(name)
            authors_str = "; ".join(author_names)

            # Volume, issue, pages
            vol_info = info.get("ref-volisspag") or {}
            volume = ""
            issue = ""
            pages = ""
            if isinstance(vol_info, dict):
                voliss = vol_info.get("voliss") or {}
                if isinstance(voliss, dict):
                    volume = str(voliss.get("@volume") or "")
                    issue = str(voliss.get("@issue") or "")
                pagerange = vol_info.get("pagerange") or {}
                if isinstance(pagerange, dict):
                    first = pagerange.get("@first") or ""
                    last = pagerange.get("@last") or ""
                    pages = f"{first}-{last}" if (first and last) else str(first)

            raw_fulltext = str(r.get("ref-fulltext") or r.get("ce:source-text") or "")
            raw_fulltext = str(r.get("ref-fulltext") or r.get("ce:source-text") or "").strip()

            if not title and raw_fulltext:
                clean_raw = re.sub(r"^\d+[\.\s]+", "", raw_fulltext).strip()
                clean_raw = re.sub(r"\[Internet\].*", "", clean_raw, flags=re.I).strip().rstrip(".,;")
                parts = [p.strip() for p in clean_raw.split(".") if p.strip()]
                if len(parts) >= 2:
                    title = ". ".join(parts[1:])
                elif parts:
                    title = parts[0]

            results.append({
                "reference_no": ref_no,
                "scopus_id": scopus_id,
                "scopus_eid": scopus_eid,
                "scopus_type": "resolvedReference" if is_linked else "unresolvedReference",
                "scopus_linked": is_linked,
                "scopus_link": scopus_link,
                "doi": doi,
                "title": title,
                "journal": journal,
                "year": year,
                "volume": volume,
                "issue": issue,
                "pages": pages,
                "authors": authors_str,
                "raw_fulltext": raw_fulltext,
            })
        return results

