"""Step 7 deterministic observed-result extraction tests."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from app.schemas.execution import ExecutionOutputRecord, ExecutionPolicy, ExecutionRecord, ExecutionStatus
from app.services.execution.extraction import extract_observed_result
from app.services.execution.sandbox import DockerRunner
from app.schemas.research import ObservedResultStatus
from tests.test_secure_execution import prepared_service, target


def record(tmp_path: Path, payload: str, name: str = "result.json", *, status: ExecutionStatus = ExecutionStatus.COMPLETED) -> ExecutionRecord:
    path = tmp_path / name
    path.write_text(payload, encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    output = ExecutionOutputRecord(name=name, sandbox_path=f"/outputs/{name}", sha256=digest, size_bytes=path.stat().st_size, output_type=name.rsplit(".", 1)[-1].upper(), provenance="fixture", storage_reference=str(path))
    return ExecutionRecord(run_id="RUN-STEP7", target_id="TARGET-FIXTURE", experiment_id="EXP-FIXTURE", artifact_id="ART-FIXTURE", timestamp_started=__import__("datetime").datetime.now(__import__("datetime").timezone.utc), timestamp_finished=__import__("datetime").datetime.now(__import__("datetime").timezone.utc), runtime_seconds=0, resource_policy=ExecutionPolicy(), sandbox={"image": "python:3.12-slim"}, status=status, outputs=(output,))


def fixture_target(metric: str | None = "accuracy"):
    return target().model_copy(update={"metric": metric})


def test_valid_json_result(tmp_path: Path) -> None:
    observed = extract_observed_result(fixture_target(), record(tmp_path, '{"metric":"accuracy","value":0.75}'))
    assert observed.status == ObservedResultStatus.EXTRACTED and observed.value == 0.75 and observed.source_output_id == "result.json"


@pytest.mark.parametrize("payload", ["{", '{"metric":"accuracy"}', '{"value":0.75}', '{"metric":"accuracy","value":"bad"}', '{"metric":"accuracy","value":NaN}', '{"metric":"accuracy","value":Infinity}'])
def test_invalid_json_is_safe(tmp_path: Path, payload: str) -> None:
    observed = extract_observed_result(fixture_target(), record(tmp_path, payload))
    assert observed.status in {ObservedResultStatus.NOT_FOUND, ObservedResultStatus.INVALID}


def test_wrong_metric_is_not_substituted(tmp_path: Path) -> None:
    observed = extract_observed_result(fixture_target("f1"), record(tmp_path, '{"metric":"accuracy","value":0.75}'))
    assert observed.status == ObservedResultStatus.NOT_FOUND


def test_duplicate_metric_is_ambiguous(tmp_path: Path) -> None:
    first = tmp_path / "a.json"; second = tmp_path / "b.json"
    first.write_text('{"metric":"accuracy","value":0.74}', encoding="utf-8"); second.write_text('{"metric":"accuracy","value":0.76}', encoding="utf-8")
    outputs = tuple(ExecutionOutputRecord(name=p.name, sandbox_path=f"/outputs/{p.name}", sha256=hashlib.sha256(p.read_bytes()).hexdigest(), size_bytes=p.stat().st_size, output_type="JSON", provenance="fixture", storage_reference=str(p)) for p in (first, second))
    run = record(tmp_path, "{}", "unused.json").model_copy(update={"outputs": outputs})
    observed = extract_observed_result(fixture_target(), run)
    assert observed.status == ObservedResultStatus.AMBIGUOUS


def test_valid_csv_result(tmp_path: Path) -> None:
    observed = extract_observed_result(fixture_target(), record(tmp_path, "metric,value\naccuracy,0.75\n", "metrics.csv"))
    assert observed.status == ObservedResultStatus.EXTRACTED and observed.extraction_method == "CSV_COLUMN"


def test_stdout_pattern_and_unrelated_numbers(tmp_path: Path) -> None:
    run = record(tmp_path, "{}").model_copy(update={"outputs": (), "stdout": "epoch 10 loss 0.23\naccuracy=0.81\n"})
    observed = extract_observed_result(fixture_target(), run)
    assert observed.value == 0.81 and observed.source_type == "EXECUTION_STDOUT"


def test_stdout_duplicate_metric_is_ambiguous(tmp_path: Path) -> None:
    run = record(tmp_path, "{}").model_copy(update={"outputs": (), "stdout": "val_accuracy=0.74\ntest_accuracy=0.76\naccuracy=0.74\naccuracy=0.76\n"})
    observed = extract_observed_result(fixture_target(), run)
    assert observed.status == ObservedResultStatus.AMBIGUOUS
    
    run2 = record(tmp_path, "{}").model_copy(update={"outputs": (), "stdout": "epoch 1 accuracy=0.5\nepoch 2 accuracy=0.6\n"})
    observed2 = extract_observed_result(fixture_target(), run2)
    assert observed2.status == ObservedResultStatus.AMBIGUOUS

    run3 = record(tmp_path, "{}").model_copy(update={"outputs": (), "stdout": "accuracy=0.75\naccuracy=0.75\n"})
    observed3 = extract_observed_result(fixture_target(), run3)
    assert observed3.status == ObservedResultStatus.AMBIGUOUS



@pytest.mark.parametrize("status", [ExecutionStatus.FAILED, ExecutionStatus.BLOCKED, ExecutionStatus.TIMED_OUT])
def test_unusable_execution_is_unavailable(tmp_path: Path, status: ExecutionStatus) -> None:
    assert extract_observed_result(fixture_target(), record(tmp_path, '{}', status=status)).status == ObservedResultStatus.UNAVAILABLE


def test_output_hash_change_is_invalid(tmp_path: Path) -> None:
    run = record(tmp_path, '{"metric":"accuracy","value":0.75}')
    run.outputs[0].storage_reference and Path(run.outputs[0].storage_reference).write_text('{"metric":"accuracy","value":0.99}', encoding="utf-8")
    assert extract_observed_result(fixture_target(), run).status == ObservedResultStatus.INVALID


def test_missing_metric_metadata_can_use_explicit_structured_metric(tmp_path: Path) -> None:
    observed = extract_observed_result(fixture_target(None), record(tmp_path, '{"metric":"accuracy","value":0.75}'))
    assert observed.metric_name == "accuracy" and observed.value == 0.75


from tests.test_secure_execution import _docker_fixture_available
@pytest.mark.skipif(not _docker_fixture_available(), reason="Docker required")
def test_real_fixture_execution_to_observed_result(tmp_path: Path) -> None:
    service, selected, _, _ = prepared_service(tmp_path, DockerRunner())
    approval = service.approve(selected.target_id, "step7-reviewer", ExecutionPolicy())
    run = service.execute(selected.target_id, approval.approval_id, ExecutionPolicy())
    observed = extract_observed_result(selected, run)
    assert run.status == ExecutionStatus.COMPLETED
    assert observed.status == ObservedResultStatus.EXTRACTED
    assert observed.value == 0.75 and observed.run_id == run.run_id and observed.target_id == selected.target_id
