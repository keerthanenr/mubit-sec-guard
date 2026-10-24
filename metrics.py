"""Score the files in results/: accuracy, per-label recall and spend per lane.

The one place that turns result rows into numbers. evaluate.py scores a live run
with it, report.py reads its files with it, and dashboard.py builds the dashboard
payload from it, so the three can never disagree.

Imports config and spend only: scoring never reaches the network.
"""
import json
from collections import Counter

import config
import spend

HOLDOUT_MODEL = "claude-opus-5-5"


def read_jsonl(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def accuracy(rows):
    """(correct, total) over rows holding `expected` and `got`."""
    return sum(r["got"] == r["expected"] for r in rows), len(rows)


def label_recall(lane, rows):
    """{label: (hit, n)} for every label the lane declares and the rows contain.

    Keeps config's label order, so printed tables stay stable across runs.
    """
    n = Counter(r["expected"] for r in rows)
    hit = Counter(r["expected"] for r in rows if r["got"] == r["expected"])
    return {label: (hit[label], n[label]) for label in config.LANES[lane].labels if n[label]}


def results_dir(model=None):
    """Where a teacher model's results live. seed.py writes this same layout."""
    root = config.ROOT / "results"
    return root / model if model else root


def split_rows(lane, split, model=None):
    """Every row of <lane>_<split>*.jsonl, so seed + seed_extra* read as one split."""
    paths = sorted(results_dir(model).glob(f"{lane}_{split}*.jsonl"))
    return [row for path in paths for row in read_jsonl(path)]


def lane_metrics(model=HOLDOUT_MODEL):
    """Seed score, holdout score, per-label recall and spend, one entry per lane."""
    ledger = spend.load()
    out = []
    for lane in config.LANES:
        seed = split_rows(lane, "seed")
        holdout = split_rows(lane, "holdout", model=model)
        s_correct, s_total = accuracy(seed)
        h_correct, h_total = accuracy(holdout)
        out.append({
            "lane": lane,
            "seed_correct": s_correct,
            "seed_total": s_total,
            "holdout_correct": h_correct,
            "holdout_total": h_total,
            "seed_recall": label_recall(lane, seed),
            "holdout_recall": label_recall(lane, holdout),
            "spend": ledger["lanes"].get(lane, {}),
        })
    return out
