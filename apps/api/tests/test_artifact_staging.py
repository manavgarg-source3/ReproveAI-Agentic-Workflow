"""Safe public repository staging tests."""

import io
import tarfile

import pytest

from app.schemas.research import ArtifactStatus, ReproductionTargetSelection
from app.services.execution.sandbox import ExecutionRejected, ExecutionService
from app.services.execution.staging import stage_target_repository
from tests.test_secure_execution import code_artifact, target


COMMIT = "b" * 40


def archive_bytes(*, unsafe_link: bool = False) -> bytes:
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz") as archive:
        if unsafe_link:
            member = tarfile.TarInfo("repository-b/external")
            member.type = tarfile.SYMTYPE
            member.linkname = "/etc/passwd"
            archive.addfile(member)
        else:
            payload = b"print('safe')\n"
            member = tarfile.TarInfo("repository-b/experiment-spring/train.py")
            member.size = len(payload)
            archive.addfile(member, io.BytesIO(payload))
    return stream.getvalue()


class Response:
    status_code = 200

    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def iter_content(self, chunk_size: int):
        del chunk_size
        yield self.payload


class Session:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.urls: list[str] = []

    def get(self, url: str, **_kwargs):
        self.urls.append(url)
        return Response(self.payload)


def prepared_service(tmp_path):
    service = ExecutionService(db_path=tmp_path / "execution.db")
    fixture_target = target().model_copy(update={"target_id": "TARGET-STAGING"})
    artifact = code_artifact().model_copy(update={
        "repository": "https://github.com/example/repository",
        "source_url": "https://github.com/example/repository",
        "commit": COMMIT,
        "availability_status": ArtifactStatus.FOUND,
    })
    service.register_selection(
        ReproductionTargetSelection(candidate_targets=[fixture_target]), [artifact]
    )
    return service, fixture_target


def test_exact_public_commit_is_safely_staged_and_registered(tmp_path) -> None:
    service, fixture_target = prepared_service(tmp_path)
    session = Session(archive_bytes())

    manifest = stage_target_repository(
        service, fixture_target.target_id, session=session
    )

    registration = service.registrations[fixture_target.target_id]
    assert registration.planned_hash == manifest
    assert (registration.source_dir / "experiment-spring/train.py").read_text() == "print('safe')\n"
    assert session.urls == [
        f"https://codeload.github.com/example/repository/tar.gz/{COMMIT}"
    ]


def test_repository_archive_links_are_rejected(tmp_path) -> None:
    service, fixture_target = prepared_service(tmp_path)

    with pytest.raises(ExecutionRejected, match="unsafe archive member"):
        stage_target_repository(
            service,
            fixture_target.target_id,
            session=Session(archive_bytes(unsafe_link=True)),
        )
