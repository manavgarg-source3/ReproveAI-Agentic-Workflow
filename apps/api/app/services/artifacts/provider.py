"""Provider-neutral public repository metadata contract."""

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class RepositoryFileMetadata:
    path: str
    is_directory: bool = False
    size: int | None = None


@dataclass(frozen=True)
class RepositoryMetadata:
    canonical_url: str
    platform: str
    owner: str
    name: str
    accessible: bool
    description: str | None = None
    default_branch: str | None = None
    latest_commit: str | None = None
    readme_excerpt: str | None = None
    visible_files: list[str] = field(default_factory=list)
    file_tree: list[RepositoryFileMetadata] = field(default_factory=list)
    inspection_partial: bool = False
    readme_available: bool = False
    requests_made: int = 0
    license_name: str | None = None
    updated_at: str | None = None
    notes: list[str] = field(default_factory=list)


class RepositoryMetadataProvider(Protocol):
    def inspect(self, repository_url: str) -> RepositoryMetadata: ...
