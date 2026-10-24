"""feedback.py <finding_id> <correct_label>: record a correction locally."""
import json
import sys
from datetime import datetime, timezone

import config
from report import read_jsonl


def submit_correction(finding, correct_label):
    # ---- STUB ---- Mubit's docs only show a Good/Bad rating in the console.
    raise NotImplementedError("Ask Mubit how to submit corrections")


def main(argv):
    if len(argv) != 3:
        sys.exit(__doc__)
    finding_id, correct_label = argv[1], argv[2]
    finding = next((f for f in read_jsonl(config.state_dir() / "findings.jsonl")
                    if f["id"] == finding_id), None)
    if finding is None:
        sys.exit(f"No finding with id {finding_id!r} in findings.jsonl")
    lane = finding.get("lane", "web_php")
    labels = config.LANES[lane].labels
    if correct_label not in labels:
        sys.exit(f"Unknown label {correct_label!r} for lane {lane}. Use one of: {', '.join(labels)}")
    entry = {
        "finding_id": finding_id,
        "lane": lane,
        "request_id": finding.get("request_id"),
        "original_label": finding["label"],
        "correct_label": correct_label,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    with open(config.state_dir() / "corrections.jsonl", "a") as f:
        f.write(json.dumps(entry) + "\n")
    print(f"Recorded ({lane}): {finding['label']} -> {correct_label} (request {entry['request_id']})")


if __name__ == "__main__":
    main(sys.argv)
