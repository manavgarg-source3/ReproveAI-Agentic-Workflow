"""Bounded staging of an exact public repository revision for Step 6."""

from __future__ import annotations

import os
import re
import shutil
import tarfile
import tempfile
from pathlib import Path, PurePosixPath
from urllib.parse import quote

import requests

from app.services.artifacts.repository import parse_repository_url
from app.services.execution.sandbox import (
    ExecutionFailureCode,
    ExecutionRejected,
    ExecutionService,
    MAX_ARTIFACT_BYTES,
    MAX_ARTIFACT_FILES,
)


MAX_ARCHIVE_BYTES = 128 * 1024 * 1024
COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$", re.IGNORECASE)


def _download_archive(
    url: str,
    destination: Path,
    *,
    session: requests.Session,
) -> None:
    try:
        response = session.get(
            url,
            headers={"User-Agent": "REPROVE-Artifact-Staging/1.0"},
            timeout=(10, 60),
            stream=True,
        )
    except requests.RequestException as exc:
        raise ExecutionRejected(
            ExecutionFailureCode.MISSING_INPUT,
            "The exact public repository snapshot could not be downloaded.",
        ) from exc
    if response.status_code != 200:
        raise ExecutionRejected(
            ExecutionFailureCode.MISSING_INPUT,
            f"The public repository snapshot returned HTTP {response.status_code}.",
        )
    total = 0
    with destination.open("wb") as output:
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            if not chunk:
                continue
            total += len(chunk)
            if total > MAX_ARCHIVE_BYTES:
                raise ExecutionRejected(
                    ExecutionFailureCode.RESOURCE_LIMIT_EXCEEDED,
                    "The compressed repository snapshot exceeds the staging limit.",
                )
            output.write(chunk)


def _extract_archive(archive_path: Path, destination: Path) -> None:
    total = 0
    seen: set[str] = set()
    try:
        archive = tarfile.open(archive_path, mode="r:gz")
    except (tarfile.TarError, OSError) as exc:
        raise ExecutionRejected(
            ExecutionFailureCode.MISSING_INPUT,
            "The repository snapshot archive is malformed.",
        ) from exc
    with archive:
        members = archive.getmembers()
        regular = [item for item in members if item.isfile()]
        if len(regular) > MAX_ARTIFACT_FILES:
            raise ExecutionRejected(
                ExecutionFailureCode.RESOURCE_LIMIT_EXCEEDED,
                "The repository snapshot contains too many files.",
            )
        roots = {
            PurePosixPath(item.name).parts[0]
            for item in members
            if PurePosixPath(item.name).parts
        }
        if len(roots) != 1:
            raise ExecutionRejected(
                ExecutionFailureCode.MISSING_INPUT,
                "The repository snapshot has an invalid archive root.",
            )
        root = next(iter(roots))
        for member in members:
            path = PurePosixPath(member.name)
            if (
                path.is_absolute()
                or ".." in path.parts
                or not path.parts
                or path.parts[0] != root
                or member.issym()
                or member.islnk()
                or member.isdev()
            ):
                raise ExecutionRejected(
                    ExecutionFailureCode.MISSING_INPUT,
                    "The repository snapshot contains an unsafe archive member.",
                )
            relative = PurePosixPath(*path.parts[1:])
            if not relative.parts or member.isdir():
                continue
            if not member.isfile():
                raise ExecutionRejected(
                    ExecutionFailureCode.MISSING_INPUT,
                    "The repository snapshot contains an unsupported archive member.",
                )
            key = relative.as_posix().casefold()
            if key in seen:
                raise ExecutionRejected(
                    ExecutionFailureCode.MISSING_INPUT,
                    "The repository snapshot contains duplicate file paths.",
                )
            seen.add(key)
            total += member.size
            if total > MAX_ARTIFACT_BYTES:
                raise ExecutionRejected(
                    ExecutionFailureCode.RESOURCE_LIMIT_EXCEEDED,
                    "The expanded repository snapshot exceeds the staging limit.",
                )
            source = archive.extractfile(member)
            if source is None:
                raise ExecutionRejected(
                    ExecutionFailureCode.MISSING_INPUT,
                    "A repository snapshot file could not be read.",
                )
            target = destination.joinpath(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as output:
                shutil.copyfileobj(source, output, length=1024 * 1024)
            os.chmod(target, 0o444)


def stage_target_repository(
    service: ExecutionService,
    target_id: str,
    *,
    session: requests.Session | None = None,
) -> str:
    """Download, validate, and register the selected target's exact commit."""

    if target_id in service.registrations:
        return service.registrations[target_id].planned_hash
    target = service.targets.get(target_id)
    if target is None or not target.code_artifact_id:
        raise ExecutionRejected(
            ExecutionFailureCode.INVALID_TARGET, "Unknown reproduction target."
        )
    artifact = service.artifacts.get(target.code_artifact_id)
    if artifact is None or not artifact.repository:
        raise ExecutionRejected(
            ExecutionFailureCode.MISSING_INPUT,
            "The selected target has no public repository source to stage.",
        )
    if not artifact.commit or not COMMIT_PATTERN.fullmatch(artifact.commit):
        raise ExecutionRejected(
            ExecutionFailureCode.MISSING_INPUT,
            "The repository must resolve to an exact commit before staging.",
        )
    platform, owner, repository = parse_repository_url(artifact.repository)
    if platform != "github":
        raise ExecutionRejected(
            ExecutionFailureCode.MISSING_INPUT,
            "Automatic execution staging currently supports public GitHub repositories only.",
        )
    archive_url = (
        f"https://codeload.github.com/{quote(owner, safe='')}/"
        f"{quote(repository, safe='')}/tar.gz/{artifact.commit}"
    )
    source_root = service.repository.path.parent / "sources" / artifact.artifact_id
    destination = source_root / artifact.commit
    if not destination.exists():
        source_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="download-", dir=source_root) as temp:
            temporary = Path(temp)
            archive_path = temporary / "repository.tar.gz"
            extracted = temporary / "extracted"
            extracted.mkdir(mode=0o700)
            _download_archive(
                archive_url,
                archive_path,
                session=session or requests.Session(),
            )
            _extract_archive(archive_path, extracted)
            os.replace(extracted, destination)
    return service.register_artifact_source(target_id, destination)
