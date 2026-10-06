"""Bounded, metadata-only inspection for explicit public GitHub/GitLab URLs."""

import base64
import json
import os
import urllib.parse
from typing import Any

import requests

from app.services.artifacts.provider import RepositoryFileMetadata, RepositoryMetadata

DEFAULT_TIMEOUT_SECONDS = 10.0
MAX_RESPONSE_BYTES = 1_000_000
MAX_README_CHARACTERS = 40_000
MAX_VISIBLE_FILES = 200
DEFAULT_MAX_DIRECTORY_DEPTH = 2
DEFAULT_MAX_METADATA_REQUESTS = 6
DEFAULT_MAX_CONTENT_REQUESTS = 4


def _positive_integer(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = int(raw)
    if value <= 0:
        raise ValueError(f"{name} must be positive.")
    return value


class RepositoryAccessError(RuntimeError):
    """A public repository could not be inspected safely."""


def parse_repository_url(url: str) -> tuple[str, str, str]:
    parsed = urllib.parse.urlsplit(url)
    host = (parsed.hostname or "").casefold()
    parts = [urllib.parse.unquote(part) for part in parsed.path.split("/") if part]
    if host not in {"github.com", "www.github.com", "gitlab.com", "www.gitlab.com"}:
        raise ValueError("Only explicit public GitHub and GitLab repository URLs are supported.")
    if len(parts) < 2:
        raise ValueError("Repository URL must include an owner and repository name.")
    platform = "github" if "github" in host else "gitlab"
    owner = parts[0] if platform == "github" else "/".join(parts[:-1])
    repository = parts[1] if platform == "github" else parts[-1]
    if repository.endswith(".git"):
        repository = repository[:-4]
    if not owner or not repository:
        raise ValueError("Repository URL is incomplete.")
    return platform, owner, repository


def normalize_repository_url(url: str) -> str:
    platform, owner, repository = parse_repository_url(url)
    host = "github.com" if platform == "github" else "gitlab.com"
    return f"https://{host}/{owner}/{repository}"


class PublicRepositoryMetadataProvider:
    """Read only bounded API metadata; never clone, download archives, or execute files."""

    def __init__(self, *, session: requests.Session | None = None, timeout: float | None = None) -> None:
        self.session = session or requests.Session()
        self.timeout = timeout or float(os.getenv("ARTIFACT_REQUEST_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS))
        if self.timeout <= 0:
            raise ValueError("ARTIFACT_REQUEST_TIMEOUT_SECONDS must be positive.")
        self.session.headers.update({
            "User-Agent": "REPROVE-Artifact-Discovery/1.0",
            "Accept": "application/json",
        })
        self.max_files = _positive_integer("MAX_REPOSITORY_FILES", MAX_VISIBLE_FILES)
        self.max_depth = _positive_integer(
            "MAX_REPOSITORY_DIRECTORY_DEPTH", DEFAULT_MAX_DIRECTORY_DEPTH
        )
        self.max_readme_characters = _positive_integer(
            "MAX_REPOSITORY_README_CHARS", MAX_README_CHARACTERS
        )
        self.max_requests = _positive_integer(
            "MAX_REPOSITORY_METADATA_REQUESTS", DEFAULT_MAX_METADATA_REQUESTS
        )
        self.max_content_requests = _positive_integer(
            "MAX_REPOSITORY_CONTENT_REQUESTS", DEFAULT_MAX_CONTENT_REQUESTS
        )
        self._requests_made = 0
        self._content_requests_made: dict[str, int] = {}
        self._cache: dict[str, RepositoryMetadata] = {}
        self._content_cache: dict[tuple[str, str], str | None] = {}

    def _response_bytes(self, url: str, *, accept: str = "application/json") -> bytes:
        if self._requests_made >= self.max_requests:
            raise RepositoryAccessError("Repository metadata request limit reached.")
        self._requests_made += 1
        response = self.session.get(
            url,
            headers={"Accept": accept},
            timeout=self.timeout,
            stream=True,
        )
        if response.status_code != 200:
            raise RepositoryAccessError(f"Public repository provider returned HTTP {response.status_code}.")
        chunks: list[bytes] = []
        total = 0
        for chunk in response.iter_content(chunk_size=65_536):
            total += len(chunk)
            if total > MAX_RESPONSE_BYTES:
                raise RepositoryAccessError("Repository metadata response exceeded the safety limit.")
            chunks.append(chunk)
        return b"".join(chunks)

    def _json(self, url: str) -> Any:
        try:
            return json.loads(self._response_bytes(url))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise RepositoryAccessError("Repository provider returned malformed metadata.") from exc

    def _content_response_bytes(self, canonical: str, url: str) -> bytes:
        requests_made = self._content_requests_made.get(canonical, 0)
        if requests_made >= self.max_content_requests:
            raise RepositoryAccessError("Repository content request limit reached.")
        self._content_requests_made[canonical] = requests_made + 1
        response = self.session.get(
            url,
            headers={"Accept": "text/plain"},
            timeout=self.timeout,
            stream=True,
        )
        if response.status_code != 200:
            raise RepositoryAccessError(
                f"Public repository provider returned HTTP {response.status_code}."
            )
        chunks: list[bytes] = []
        total = 0
        for chunk in response.iter_content(chunk_size=65_536):
            total += len(chunk)
            if total > MAX_RESPONSE_BYTES:
                raise RepositoryAccessError("Repository file exceeded the safety limit.")
            chunks.append(chunk)
        return b"".join(chunks)

    def inspect(self, repository_url: str) -> RepositoryMetadata:
        canonical = normalize_repository_url(repository_url)
        if canonical in self._cache:
            return self._cache[canonical]
        platform, owner, repository = parse_repository_url(canonical)
        self._requests_made = 0
        try:
            if platform == "github":
                result = self._github(canonical, owner, repository)
            else:
                result = self._gitlab(canonical, owner, repository)
        except (requests.RequestException, RepositoryAccessError, ValueError) as exc:
            result = RepositoryMetadata(
                canonical_url=canonical,
                platform=platform,
                owner=owner,
                name=repository,
                accessible=False,
                requests_made=self._requests_made,
                notes=["Public repository metadata could not be retrieved."],
            )
        self._cache[canonical] = result
        return result

    def _github(self, canonical: str, owner: str, repository: str) -> RepositoryMetadata:
        api = f"https://api.github.com/repos/{urllib.parse.quote(owner)}/{urllib.parse.quote(repository)}"
        metadata = self._json(api)
        branch = str(metadata.get("default_branch") or "main")
        notes: list[str] = []
        try:
            tree_data = self._json(
                f"{api}/git/trees/{urllib.parse.quote(branch)}?recursive=1"
            )
        except (requests.RequestException, RepositoryAccessError):
            tree_data = {"tree": [], "truncated": True}
            notes.append("Repository file tree could not be retrieved.")
        raw_tree = tree_data.get("tree", []) if isinstance(tree_data, dict) else []
        bounded_tree: list[RepositoryFileMetadata] = []
        eligible_count = 0
        for item in raw_tree:
            path = str(item.get("path") or "").strip("/")
            if not path or path.count("/") > self.max_depth:
                continue
            eligible_count += 1
            if len(bounded_tree) >= self.max_files:
                continue
            bounded_tree.append(RepositoryFileMetadata(
                path=path,
                is_directory=item.get("type") == "tree",
                size=(item.get("size") if isinstance(item.get("size"), int) else None),
            ))
        files = [
            item.path for item in bounded_tree
            if not item.is_directory and "/" not in item.path
        ]
        partial = bool(tree_data.get("truncated")) or eligible_count > self.max_files

        readme_excerpt = None
        readme_path = None
        try:
            readme = self._json(f"{api}/readme")
            if readme.get("encoding") == "base64" and readme.get("content"):
                decoded = base64.b64decode(readme["content"], validate=False).decode("utf-8", errors="replace")
                readme_excerpt = decoded[:self.max_readme_characters]
                reported_path = str(readme.get("path") or "").strip("/")
                if reported_path:
                    readme_path = reported_path
                else:
                    readme_path = next(
                        (
                            item.path for item in bounded_tree
                            if not item.is_directory
                            and "/" not in item.path
                            and item.path.casefold().startswith("readme")
                        ),
                        None,
                    )
        except (requests.RequestException, RepositoryAccessError):
            notes.append("Repository README could not be retrieved.")

        latest_commit = None
        try:
            commits = self._json(f"{api}/commits?per_page=1")
            if isinstance(commits, list) and commits:
                latest_commit = str(commits[0].get("sha") or "") or None
        except (requests.RequestException, RepositoryAccessError):
            notes.append("Latest repository commit could not be retrieved.")

        license_data = metadata.get("license") or {}
        return RepositoryMetadata(
            canonical_url=canonical,
            platform="github",
            owner=owner,
            name=str(metadata.get("name") or repository),
            accessible=True,
            description=metadata.get("description"),
            default_branch=branch,
            latest_commit=latest_commit,
            readme_excerpt=readme_excerpt,
            readme_path=readme_path,
            visible_files=files,
            file_tree=bounded_tree,
            inspection_partial=partial,
            readme_available=readme_excerpt is not None,
            requests_made=self._requests_made,
            license_name=license_data.get("spdx_id") or license_data.get("name"),
            updated_at=metadata.get("updated_at"),
            notes=notes,
        )

    def _gitlab(self, canonical: str, owner: str, repository: str) -> RepositoryMetadata:
        project_path = urllib.parse.quote(f"{owner}/{repository}", safe="")
        api = f"https://gitlab.com/api/v4/projects/{project_path}"
        metadata = self._json(api)
        branch = metadata.get("default_branch") or "main"
        notes: list[str] = []
        try:
            tree = self._json(
                f"{api}/repository/tree?recursive=true&per_page={self.max_files + 1}"
                f"&ref={urllib.parse.quote(branch)}"
            )
        except (requests.RequestException, RepositoryAccessError):
            tree = []
            notes.append("Repository file tree could not be retrieved.")
        bounded_tree: list[RepositoryFileMetadata] = []
        eligible_count = 0
        for item in tree:
            path = str(item.get("path") or item.get("name") or "").strip("/")
            if not path or path.count("/") > self.max_depth:
                continue
            eligible_count += 1
            if len(bounded_tree) >= self.max_files:
                continue
            bounded_tree.append(RepositoryFileMetadata(
                path=path,
                is_directory=item.get("type") == "tree",
                size=None,
            ))
        files = [
            item.path for item in bounded_tree
            if not item.is_directory and "/" not in item.path
        ]
        partial = eligible_count > self.max_files or not tree

        readme_excerpt = None
        readme_name = next((name for name in files if name.casefold().startswith("readme")), None)
        if readme_name:
            try:
                encoded_file = urllib.parse.quote(readme_name, safe="")
                raw = self._response_bytes(
                    f"{api}/repository/files/{encoded_file}/raw?ref={urllib.parse.quote(branch)}",
                    accept="text/plain",
                )
                readme_excerpt = raw.decode("utf-8", errors="replace")[:self.max_readme_characters]
            except (requests.RequestException, RepositoryAccessError):
                notes.append("Repository README could not be retrieved.")

        return RepositoryMetadata(
            canonical_url=canonical,
            platform="gitlab",
            owner=owner,
            name=str(metadata.get("name") or repository),
            accessible=True,
            description=metadata.get("description"),
            default_branch=branch,
            latest_commit=(metadata.get("last_activity_at") or None),
            readme_excerpt=readme_excerpt,
            readme_path=readme_name,
            visible_files=files,
            file_tree=bounded_tree,
            inspection_partial=partial,
            readme_available=readme_excerpt is not None,
            requests_made=self._requests_made,
            license_name=(metadata.get("license") or {}).get("name"),
            updated_at=metadata.get("last_activity_at"),
            notes=notes,
        )

    def get_file_content(self, repository_url: str, path: str) -> str | None:
        """Fetch the bounded content of a specific file."""
        canonical = normalize_repository_url(repository_url)
        cache_key = (canonical, path.casefold())
        if cache_key in self._content_cache:
            return self._content_cache[cache_key]
        metadata = self.inspect(canonical)
        if not metadata.accessible:
            return None
        visible_paths = {
            item.path.casefold() for item in metadata.file_tree if not item.is_directory
        }
        if visible_paths and path.casefold() not in visible_paths:
            self._content_cache[cache_key] = None
            return None
        if (
            metadata.readme_path is not None
            and path.casefold() == metadata.readme_path.casefold()
            and metadata.readme_excerpt is not None
        ):
            self._content_cache[cache_key] = metadata.readme_excerpt
            return metadata.readme_excerpt

        branch = metadata.default_branch or "main"
        try:
            if metadata.platform == "github":
                api = f"https://raw.githubusercontent.com/{metadata.owner}/{metadata.name}/{branch}/{urllib.parse.quote(path)}"
                raw = self._content_response_bytes(canonical, api)
            else:
                project_path = urllib.parse.quote(f"{metadata.owner}/{metadata.name}", safe="")
                encoded_file = urllib.parse.quote(path, safe="")
                api = f"https://gitlab.com/api/v4/projects/{project_path}/repository/files/{encoded_file}/raw?ref={urllib.parse.quote(branch)}"
                raw = self._content_response_bytes(canonical, api)
            result = raw.decode("utf-8", errors="replace")[:self.max_readme_characters]
            self._content_cache[cache_key] = result
            return result
        except (requests.RequestException, RepositoryAccessError):
            self._content_cache[cache_key] = None
            return None

