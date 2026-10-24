"""classify(snippet, session_id, lane) -> (label, request_id), via Mubit."""
import re
import time

import config
import spend

UNPARSEABLE = "unparseable"

# Offline stub: crude regexes so tests and --dry-run work without the network.
_USER_INPUT = r"\$_(?:GET|POST|REQUEST|COOKIE|FILES)|php://input"
_OFFLINE_RULES = {
    "web_php": [
        ("unsafe_deserialization", re.compile(r"\bunserialize\s*\(")),
        ("path_traversal", re.compile(
            r"(?:\b(?:include|require)(?:_once)?\b|readfile|file_get_contents|fopen|unlink|parse_ini_file|move_uploaded_file)"
            r"[^;]*(?:" + _USER_INPUT + r")")),
        ("sql_injection", re.compile(
            r"(?i)[\"'](?:select|insert|update|delete)\b[^\"']*(?:\$\w|[\"']\s*\.\s*\$)")),
        ("xss", re.compile(r"(?:\becho\b|\bprint\b|printf|<\?=)[^;]*(?:" + _USER_INPUT + r")")),
        ("hardcoded_secret", re.compile(
            r"(?i)(?:password|passwd|secret|token|api_?key)\w*['\"]?\s*(?:=>|=|,)\s*['\"][^'\"]{8,}['\"]")),
    ],
    "ai_app": [
        ("hardcoded_secret", re.compile(
            r"(?i)(?:api_?key|secret|token)\w*\s*=\s*['\"][^'\"]{12,}['\"]")),
        ("unsafe_output_handling", re.compile(
            r"\b(?:eval|exec|os\.system|subprocess\.\w+)\s*\(")),
        ("excessive_agency", re.compile(
            r"(?i)rmtree|os\.remove|drop\s+table|\.delete\(|transfer_funds|send_email")),
        ("prompt_injection", re.compile(
            r"(?s)[\"']system[\"'][^}]*?(?:f[\"']|\+\s*\w|\.format\()|system\s*=\s*f[\"']")),
    ],
    "agent_app": [
        ("unexpected_code_execution", re.compile(r"\b(?:exec|eval)\s*\(|subprocess\.\w+\(.*shell=True")),
        ("memory_poisoning", re.compile(r"(?i)memory\.(?:add|save|store|append|put)\(")),
        ("insecure_agent_comms", re.compile(r"http://")),
        ("privilege_abuse", re.compile(r"(?i)admin_token|ADMIN_|root_|org:admin|scopes?=\[?[\"']\*")),
    ],
    "rag_app": [
        ("hidden_context_exposure", re.compile(r"(?i)system[^\n]*(?:password|FAKE|secret)")),
        ("untrusted_ingestion", re.compile(r"(?i)(?:add_documents|upsert|add_texts)\([^)]*(?:upload|scrap|email)")),
    ],
    "ml_code": [
        ("unsafe_model_loading", re.compile(
            r"pickle\.loads?\(|joblib\.load\(|trust_remote_code\s*=\s*True|torch\.load\((?![^)]*weights_only\s*=\s*True)")),
        ("model_exposure", re.compile(r"predict_proba|logits")),
    ],
    "data_science": [
        ("hardcoded_secret", re.compile(r"(?i)(?:key|token|password|secret)\w*\s*=\s*['\"][^'\"]{8,}['\"]|://\w+:[^@/]+@")),
        ("unsafe_deserialization", re.compile(r"read_pickle|pickle\.load|joblib\.load|yaml\.load\((?![^)]*SafeLoader)")),
        ("untrusted_data_source", re.compile(r"[\"']http://")),
        ("injection", re.compile(r"(?i)f[\"'](?:select|insert|update|delete)\b|\.query\(f[\"']|os\.system\(")),
    ],
    "mcp_server": [
        ("tool_poisoning", re.compile(r"(?i)<important>|ignore previous|do not tell the user")),
        ("unverified_server", re.compile(r"npx\s+-y|@latest|[\"']http://")),
        ("excessive_tool_scope", re.compile(r"(?i)run_command|shell=True|root\s*=\s*[\"']/[\"']")),
    ],
    "data_pipeline": [
        ("data_in_transit_exposure", re.compile(r"(?i)sslmode=disable|verify=False|[\"']http://|PLAINTEXT|ftp://")),
        ("insecure_data_storage", re.compile(r"(?i)public-read|allUsers|block_public_acls\s*=\s*false")),
        ("excessive_data_access", re.compile(r"(?i)grant\s+all|roles/owner|ACCOUNTADMIN|[\"']s3:\*[\"']")),
        ("pipeline_injection", re.compile(r"(?i)f[\"'](?:create|insert|copy|alter)\b")),
    ],
}


def truncate(snippet):
    return snippet[: config.MAX_SNIPPET_CHARS]


def build_messages(snippet, lane="web_php"):
    # The system message is always the lane's instruction constant; only the user message varies.
    return [
        {"role": "system", "content": config.LANES[lane].instruction},
        {"role": "user", "content": truncate(snippet)},
    ]


def parse_label(reply, lane="web_php"):
    label = (reply or "").strip().lower().strip("`'\".")
    return label if label in config.LANES[lane].labels else UNPARSEABLE


def _offline_classify(snippet, lane):
    for label, pattern in _OFFLINE_RULES.get(lane, []):
        if pattern.search(snippet):
            if label == "xss" and "htmlspecialchars" in snippet:
                continue
            if label == "path_traversal" and "basename(" in snippet:
                continue
            return label
    if lane == "ai_app" and ".create(" in snippet and "max_tokens" not in snippet:
        return "unbounded_consumption"
    return "none"


def make_client():
    from openai import OpenAI

    return OpenAI(
        base_url=config.base_url(),
        api_key=config.api_key(),
        timeout=config.TIMEOUT_SECONDS,
        max_retries=0,  # retries are handled below so retry-after is honoured
    )


def make_anthropic_client():
    import os

    import anthropic

    # Mubit refuses a call that carries any other Anthropic credential beside the
    # Mubit key, and the SDK would pick these up from the environment.
    os.environ.pop("ANTHROPIC_AUTH_TOKEN", None)
    os.environ.pop("ANTHROPIC_API_KEY", None)
    return anthropic.Anthropic(
        base_url=config.base_url(),
        api_key=config.api_key(),
        timeout=config.TIMEOUT_SECONDS,
        max_retries=0,
    )


def _retry_after(error):
    try:
        return float(error.response.headers.get("retry-after", "1"))
    except (TypeError, ValueError):
        return 1.0


def _call_openai(messages, session_id, extra_headers):
    kwargs = {}
    # Gemini rejects a "metadata" field, and Mubit documents no session field for
    # Gemini (it derives the session from the conversation start).
    if not config.gemini_route():
        kwargs["metadata"] = {"session_id": session_id}
    if extra_headers:
        kwargs["extra_headers"] = extra_headers
    raw = make_client().chat.completions.with_raw_response.create(
        model=config.model(), messages=messages, temperature=config.TEMPERATURE, **kwargs)
    response = raw.parse()
    usage = response.usage
    tokens = (usage.prompt_tokens or 0, usage.completion_tokens or 0) if usage else None
    return raw, response.choices[0].message.content, tokens


def _call_anthropic(messages, session_id, extra_headers):
    kwargs = {"extra_headers": extra_headers} if extra_headers else {}
    kwargs.update(config.anthropic_options())
    raw = make_anthropic_client().messages.with_raw_response.create(
        model=config.model(),
        max_tokens=config.reply_tokens(),
        # No temperature: the Anthropic API now rejects it for this model ("Extra inputs are
        # not permitted"). Seeding uses --agree-only instead to keep recorded labels correct.
        system=messages[0]["content"],
        messages=messages[1:],
        # metadata.user_id is the session field Mubit reads on the Anthropic route.
        metadata={"user_id": session_id},
        **kwargs,
    )
    message = raw.parse()
    text = "".join(block.text for block in message.content if block.type == "text")
    return raw, text, (message.usage.input_tokens, message.usage.output_tokens)


def _status_error_types():
    types = []
    for module in ("openai", "anthropic"):
        try:
            types.append(__import__(module).APIStatusError)
        except ImportError:
            pass
    return tuple(types)


def classify(snippet, session_id, lane="web_php", store=True):
    """store=False sends x-middleware-store: false, so Mubit keeps no record of the
    call (used for holdout snippets, which must not be recorded or trained on)."""
    if config.offline():
        return _offline_classify(truncate(snippet), lane), "offline"

    messages = build_messages(snippet, lane)
    call = _call_anthropic if config.anthropic_route() else _call_openai
    extra_headers = None if store else {"x-middleware-store": "false"}
    attempt = 0
    while True:
        spend.check(spend.estimate(messages))
        try:
            raw, reply, tokens = call(messages, session_id, extra_headers)
            break
        except _status_error_types() as e:
            if e.status_code in (429, 503) and attempt < config.MAX_RETRIES:
                attempt += 1
                time.sleep(_retry_after(e))
                continue
            raise
    if tokens is not None:
        spend.record(lane, *tokens)
    return parse_label(reply, lane), raw.headers.get("x-middleware-request-id")
