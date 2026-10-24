"""Run data/<lane>/holdout.jsonl through classify and score it per lane."""
from collections import Counter

import config
from seed import parse_args, print_spend, run_batch


def summarize(lane, results):
    total = len(results)
    correct = sum(r["got"] == r["expected"] for r in results)
    print(f"\n### {lane}: accuracy {correct}/{total} = {correct / total:.0%}\n" if total
          else f"\n### {lane}: no results.")

    n = Counter(r["expected"] for r in results)
    hit = Counter(r["expected"] for r in results if r["got"] == r["expected"])
    print(f"{'label':<26}{'n':>4}{'correct':>9}{'recall':>8}")
    for label in config.LANES[lane].labels:
        if n[label]:
            print(f"{label:<26}{n[label]:>4}{hit[label]:>9}{hit[label] / n[label]:>8.0%}")

    misses = [r for r in results if r["got"] != r["expected"]]
    false_negatives = [r for r in misses if r["expected"] != "none" and r["got"] == "none"]
    other = [r for r in misses if r not in false_negatives]

    print(f"\nFALSE NEGATIVES in {lane} (vulnerability classified as none): {len(false_negatives)}")
    for r in false_negatives:
        print(f"  expected={r['expected']}  id={r['request_id']}\n    {r['snippet'][:120]!r}")
    print(f"\nOther mistakes in {lane}: {len(other)}")
    for r in other:
        print(f"  expected={r['expected']} got={r['got']}  id={r['request_id']}\n    {r['snippet'][:120]!r}")


if __name__ == "__main__":
    args = parse_args(__doc__)
    for lane in args.lanes:
        # Holdout snippets must not be recorded or trained on.
        summarize(lane, run_batch(lane, "holdout", store=False))
    print_spend()
