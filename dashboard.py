"""Build the VulHawk run dashboard from results/*.jsonl and spend.json.

Reads the scores metrics.py computes and writes them into assets/dashboard.html,
which holds the whole page and keeps `/*__DATA__*/` where the data goes. Nothing
in the page is hand-typed, so it cannot drift from the files it describes.

  python dashboard.py                      -> results/dashboard.html
  python dashboard.py --publish            -> also docs/dashboard.html (committed)
  python dashboard.py --model <model-dir>  -> score another teacher model's holdout
"""
import argparse
import json
from datetime import date
from pathlib import Path

import config
import metrics

TEMPLATE = config.ROOT / "assets" / "dashboard.html"
DEFAULT_OUT = config.ROOT / "results" / "dashboard.html"
PUBLISHED = config.ROOT / "docs" / "dashboard.html"
# The whole expression, so the unfilled template stays valid JS (DATA === null).
PLACEHOLDER = "/*__DATA__*/null"

# Display name per lane. config.LANES owns the lanes; this owns only their titles.
TITLES = {
    "web_php": "Web PHP",
    "ai_app": "AI App",
    "agent_app": "Agent App",
    "rag_app": "RAG App",
    "ml_code": "ML Code",
    "data_science": "Data Science",
    "mcp_server": "MCP Server",
    "data_pipeline": "Data Pipeline",
    "web_app": "Web App",
    "api_security": "API Security",
    "cicd": "CI/CD",
    "k8s_iac": "K8s / IaC",
}


def rate(correct, total):
    return correct / total if total else 0.0


def payload(model):
    """The dashboard's data: one entry per lane, per-label recall, and the totals."""
    scored = [m for m in metrics.lane_metrics(model=model) if m["seed_total"]]
    lanes = [{
        "id": m["lane"],
        "lbl": TITLES.get(m["lane"], m["lane"]),
        "sAcc": rate(m["seed_correct"], m["seed_total"]),
        "sC": m["seed_correct"],
        "sN": m["seed_total"],
        "hAcc": rate(m["holdout_correct"], m["holdout_total"]),
        "hC": m["holdout_correct"],
        "hN": m["holdout_total"],
        "usd": m["spend"].get("usd", 0.0),
        "calls": m["spend"].get("calls", 0),
    } for m in scored]
    recall = {m["lane"]: {label: rate(hit, n) for label, (hit, n) in m["seed_recall"].items()}
              for m in scored}
    holdout_rates = [l["hAcc"] for l in lanes if l["hN"]]
    return {
        "lanes": lanes,
        "recall": recall,
        "summary": {
            "lanes": len(lanes),
            "samples": sum(l["sN"] + l["hN"] for l in lanes),
            "usd": sum(l["usd"] for l in lanes),
            "calls": sum(l["calls"] for l in lanes),
            "holdout_accuracy": sum(holdout_rates) / len(holdout_rates) if holdout_rates else 0.0,
            "base_model": config.DEFAULT_MODEL,
            "holdout_model": model,
            "generated": date.today().isoformat(),
        },
    }


def render(model):
    template = TEMPLATE.read_text()
    if PLACEHOLDER not in template:
        raise SystemExit(f"{TEMPLATE.name} has no {PLACEHOLDER} to fill")
    # </script> inside the JSON would close the page's script block early.
    data = json.dumps(payload(model), separators=(",", ":")).replace("</", "<\\/")
    return template.replace(PLACEHOLDER, data, 1)


def write(html, path):
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html)
    shown = path.relative_to(config.ROOT) if path.is_relative_to(config.ROOT) else path
    print(f"wrote {shown} ({len(html):,} bytes)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", default=metrics.HOLDOUT_MODEL,
                        help=f"results/<model>/ holding the holdout runs (default {metrics.HOLDOUT_MODEL})")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT,
                        help="where to write the dashboard (default results/dashboard.html)")
    parser.add_argument("--publish", action="store_true",
                        help=f"also write {PUBLISHED.relative_to(config.ROOT)}, the committed snapshot")
    args = parser.parse_args()

    html = render(args.model)
    write(html, args.out)
    if args.publish:
        write(html, PUBLISHED)
