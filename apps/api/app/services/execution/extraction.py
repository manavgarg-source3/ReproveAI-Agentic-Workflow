"""Deterministic, bounded extraction of observed metrics from Step 6 evidence."""
from __future__ import annotations

import csv
import io
import json
import math
import re
from pathlib import Path
from uuid import uuid4

from app.schemas.execution import ExecutionRecord, ExecutionStatus
from app.schemas.research import ArtifactConfidence, Certainty, ObservedResult, ObservedResultStatus, ReproductionTarget

MAX_BYTES = 8 * 1024 * 1024
MAX_ROWS = 1000
NUMBER = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"


def _base(target: ReproductionTarget, run: ExecutionRecord, status: ObservedResultStatus, **kwargs: object) -> ObservedResult:
    metric_name = kwargs.pop("metric_name", target.metric)
    return ObservedResult(
        observed_result_id=f"OBS-{uuid4().hex.upper()}", run_id=run.run_id,
        target_id=target.target_id, experiment_id=target.experiment_id,
        metric_name=metric_name, dataset=target.dataset.dataset_name if target.dataset else None,
        dataset_version=target.dataset_version, dataset_split=target.dataset.split if target.dataset else None,
        model=target.model.name if target.model else None, model_version=target.model_version,
        checkpoint=target.checkpoint.name if target.checkpoint else None,
        evaluation_protocol=target.evaluation_protocol, execution_type=run.execution_type.value,
        status=status, **kwargs,
    )


def _numeric(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def extract_observed_result(target: ReproductionTarget, run: ExecutionRecord) -> ObservedResult:
    if run.status != ExecutionStatus.COMPLETED:
        return _base(target, run, ObservedResultStatus.UNAVAILABLE, notes=[f"Execution status was {run.status.value}; no usable result evidence exists."])
    metric = (target.metric or "").strip()
    candidates: list[ObservedResult] = []
    for output in run.outputs:
        reference = output.storage_reference
        if not reference:
            continue
        path = Path(reference)
        try:
            if not path.is_file() or path.stat().st_size > MAX_BYTES:
                continue
            if output.sha256 and _sha256(path) != output.sha256:
                return _base(target, run, ObservedResultStatus.INVALID, warnings=[f"Output hash mismatch for {output.name}."], source_type="EXECUTION_OUTPUT_FILE", source_location=output.name, source_output_id=output.name)
            raw = path.read_bytes()
        except OSError:
            continue
        if path.suffix.casefold() == ".json":
            candidates.extend(_json_candidates(target, run, output.name, raw, metric))
        elif path.suffix.casefold() == ".csv":
            candidates.extend(_csv_candidates(target, run, output.name, raw, metric))
    if candidates:
        if len(candidates) > 1:
            return _base(target, run, ObservedResultStatus.AMBIGUOUS, warnings=["Multiple incompatible observations matched the target metric."], evidence="; ".join(item.evidence or "" for item in candidates))
        return candidates[0]
    # Training programs commonly print one authoritative summary without a
    # colon (for example, "Final test loss 3.59e-02 +/- 1.83e-03"). Prefer
    # these final summaries over per-step metrics to avoid false ambiguity.
    metric_tokens = re.findall(r"[A-Za-z0-9]+", metric)
    metric_pattern = r"[\s_-]+".join(re.escape(token) for token in metric_tokens)
    final_candidates: list[ObservedResult] = []
    if metric_pattern:
        final_pattern = re.compile(
            rf"(?i)\bfinal\s+{metric_pattern}\s*(?::|=)?\s*({NUMBER})"
            rf"(?:\s*(?:\+/-|±)\s*({NUMBER}))?"
        )
        for line_number, line in enumerate(run.stdout.splitlines(), start=1):
            match = final_pattern.search(line)
            if not match:
                continue
            value = _numeric(match.group(1))
            if value is None:
                continue
            uncertainty = match.group(2)
            final_candidates.append(_base(
                target,
                run,
                ObservedResultStatus.EXTRACTED,
                value=value,
                raw_value=match.group(1),
                source_type="EXECUTION_STDOUT",
                source_location=f"stdout line {line_number}",
                extraction_method="FINAL_STDOUT_REGEX",
                certainty=Certainty.EXPLICIT,
                confidence=ArtifactConfidence.HIGH,
                evidence=line,
                notes=([f"Reported uncertainty: +/- {uncertainty}"] if uncertainty else []),
            ))
    if final_candidates:
        if len(final_candidates) > 1:
            return _base(
                target,
                run,
                ObservedResultStatus.AMBIGUOUS,
                warnings=["Multiple final observations matched the target metric in stdout."],
                evidence="; ".join(item.evidence or "" for item in final_candidates),
            )
        return final_candidates[0]
    stdout_candidates: list[ObservedResult] = []
    for line_number, line in enumerate(run.stdout.splitlines(), start=1):
        match = re.search(rf"(?i)(?<![\w]){re.escape(metric)}\s*[:=]\s*({NUMBER})(?![\w])", line)
        if match:
            value = _numeric(match.group(1))
            if value is not None:
                stdout_candidates.append(_base(target, run, ObservedResultStatus.EXTRACTED, value=value, raw_value=match.group(1), source_type="EXECUTION_STDOUT", source_location=f"stdout line {line_number}", extraction_method="STDOUT_REGEX", certainty=Certainty.EXPLICIT, confidence=ArtifactConfidence.HIGH, evidence=line))
    if stdout_candidates:
        if len(stdout_candidates) > 1:
            return _base(target, run, ObservedResultStatus.AMBIGUOUS, warnings=["Multiple incompatible observations matched the target metric in stdout."], evidence="; ".join(item.evidence or "" for item in stdout_candidates))
        return stdout_candidates[0]
    return _base(target, run, ObservedResultStatus.NOT_FOUND, notes=["No structured output or target-matched stdout metric was found."])


def _json_candidates(target: ReproductionTarget, run: ExecutionRecord, filename: str, raw: bytes, metric: str) -> list[ObservedResult]:
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return []
    if not isinstance(data, dict):
        return []
    found: list[ObservedResult] = []
    reported_metric = str(data.get("metric", "")).strip()
    if reported_metric and (not metric or reported_metric.casefold() == metric.casefold()) and "value" in data:
        value = _numeric(data["value"])
        if value is not None:
            found.append(_base(target, run, ObservedResultStatus.EXTRACTED, metric_name=reported_metric, value=value, raw_value=str(data["value"]), source_type="STRUCTURED_RESULT", source_location=f"{filename}:$.value", source_output_id=filename, extraction_method="JSON_PATH", certainty=Certainty.EXPLICIT, confidence=ArtifactConfidence.HIGH, evidence=f"{filename} $.metric={data['metric']}; $.value={data['value']}"))
    return found


def _csv_candidates(target: ReproductionTarget, run: ExecutionRecord, filename: str, raw: bytes, metric: str) -> list[ObservedResult]:
    try:
        rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8")), strict=True))[:MAX_ROWS]
    except (UnicodeDecodeError, csv.Error):
        return []
    found: list[ObservedResult] = []
    for index, row in enumerate(rows, start=2):
        name = row.get("metric") or row.get("name")
        value_raw = row.get("value") or row.get("score")
        if name and name.casefold() == metric.casefold() and value_raw is not None:
            value = _numeric(value_raw)
            if value is not None:
                found.append(_base(target, run, ObservedResultStatus.EXTRACTED, value=value, raw_value=value_raw, source_type="TABULAR_RESULT", source_location=f"{filename} row {index}", source_output_id=filename, extraction_method="CSV_COLUMN", certainty=Certainty.EXPLICIT, confidence=ArtifactConfidence.HIGH, evidence=f"{filename} row {index}: {name}={value_raw}"))
    return found


def _sha256(path: Path) -> str:
    import hashlib
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
