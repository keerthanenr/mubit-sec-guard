"""Print the "common issues" tally per lane, plus per-lane spend."""
from collections import Counter

import config
import spend
from metrics import read_jsonl


def print_tally(title, counter):
    print(f"  {title}")
    if not counter:
        print("    (no data)")
    for label, count in counter.most_common():
        print(f"    {label:<26}{count:>5}")


if __name__ == "__main__":
    findings = read_jsonl(config.state_dir() / "findings.jsonl")
    ledger = spend.load()
    for lane in config.LANES:
        print(f"\n== {lane}")
        lane_findings = [f for f in findings if f.get("lane", "web_php") == lane]
        print_tally("Hook findings by label", Counter(f["label"] for f in lane_findings))
        print_tally("Hook decisions", Counter(f["decision"] for f in lane_findings))
        for split in ("seed", "holdout"):
            rows = read_jsonl(config.ROOT / "results" / f"{lane}_{split}.jsonl")
            print_tally(f"Classifier output ({split})", Counter(r["got"] for r in rows))
        s = ledger["lanes"].get(lane, {})
        print(f"  Spend: {s.get('calls', 0)} calls, {s.get('input_tokens', 0)} in / "
              f"{s.get('output_tokens', 0)} out tokens, est. ${s.get('usd', 0.0):.4f}")
    print(f"\nTotal est. spend: ${ledger['total_usd']:.4f} of ${config.budget_usd():.2f} cap")
