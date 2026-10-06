"""EXECUTION_INFRASTRUCTURE_FIXTURE: deterministic metric only."""

import argparse
import json
from pathlib import Path


parser = argparse.ArgumentParser()
parser.add_argument("--input", required=True)
parser.add_argument("--output", required=True)
args = parser.parse_args()

payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
labels = payload["labels"]
predictions = payload["predictions"]
if len(labels) != len(predictions) or not labels:
    raise ValueError("labels and predictions must have equal non-zero length")
accuracy = sum(left == right for left, right in zip(labels, predictions)) / len(labels)
Path(args.output).write_text(
    json.dumps({"metric": "accuracy", "value": accuracy}, sort_keys=True),
    encoding="utf-8",
)
print(json.dumps({"metric": "accuracy", "value": accuracy}, sort_keys=True))
