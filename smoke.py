"""ONE real call to Mubit with a harmless snippet: smoke.py [web_php|ai_app]."""
import sys
from datetime import date

import classifier
import config
import spend

SNIPPETS = {
    "web_php": "function add(int $a, int $b): int {\n    return $a + $b;\n}",
    "ai_app": "def word_count(text: str) -> int:\n    return len(text.split())",
}

if __name__ == "__main__":
    lane = sys.argv[1] if len(sys.argv) > 1 else "web_php"
    if lane not in config.LANES:
        sys.exit(f"Unknown lane {lane!r}. Use one of: {', '.join(config.LANES)}")
    if config.offline():
        sys.exit("GUARD_OFFLINE=1 is set; unset it for the smoke test.")
    if not config.api_key():
        sys.exit("MUBIT_API_KEY is not set (put it in .env)")
    label, request_id = classifier.classify(SNIPPETS[lane], f"smoke-{lane}-{date.today().isoformat()}", lane)
    print(f"lane:       {lane}")
    print(f"model:      {config.model()}")
    print(f"label:      {label}")
    print(f"request_id: {request_id}")
    print(f"est. spend: ${spend.load()['total_usd']:.6f} total")
