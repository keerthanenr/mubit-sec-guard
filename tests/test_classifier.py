"""Classifier, lane and spend tests with a fake OpenAI client (no network)."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx2 as httpx  # noqa: E402  (installed with openai 3.x)
import openai  # noqa: E402

import classifier  # noqa: E402
import config  # noqa: E402
import local_checks  # noqa: E402
import spend  # noqa: E402


class FakeRaw:
    def __init__(self, reply, request_id):
        self.headers = {"x-middleware-request-id": request_id}
        self._reply = reply

    def parse(self):
        message = mock.Mock(content=self._reply)
        usage = mock.Mock(prompt_tokens=100, completion_tokens=4)
        return mock.Mock(choices=[mock.Mock(message=message)], usage=usage)


class FakeClient:
    def __init__(self, replies):
        self.calls = []
        self.replies = list(replies)
        self.chat = mock.Mock()
        self.chat.completions.with_raw_response.create = self.create

    def create(self, **kwargs):
        self.calls.append(kwargs)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return FakeRaw(reply, f"req-{len(self.calls)}")


class FakeAnthropicRaw:
    def __init__(self, reply, request_id):
        self.headers = {"x-middleware-request-id": request_id}
        self._reply = reply

    def parse(self):
        block = mock.Mock(type="text", text=self._reply)
        usage = mock.Mock(input_tokens=120, output_tokens=3)
        return mock.Mock(content=[block], usage=usage)


class FakeAnthropic:
    def __init__(self, replies):
        self.calls = []
        self.replies = list(replies)
        self.messages = mock.Mock()
        self.messages.with_raw_response.create = self.create

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return FakeAnthropicRaw(self.replies.pop(0), f"areq-{len(self.calls)}")


def rate_limited(retry_after):
    response = httpx.Response(429, headers={"retry-after": retry_after},
                              request=httpx.Request("POST", "http://test/v1/chat/completions"))
    return openai.RateLimitError("rate limited", response=response, body=None)


class OnlineTest(unittest.TestCase):
    """Base: online mode, default route, spend ledger in a temp dir."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        env = {"GUARD_OFFLINE": "0", "MUBIT_BASE_URL": config.DEFAULT_BASE_URL,
               "MUBIT_MODEL": "claude-haiku-4-5", "GUARD_STATE_DIR": self.tmp.name,
               "GUARD_BUDGET_USD": "50"}
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    def classify_with(self, replies, snippets, lane="web_php"):
        fake = FakeClient(replies)
        with mock.patch.object(classifier, "make_client", return_value=fake):
            results = [classifier.classify(s, f"session-{i}", lane) for i, s in enumerate(snippets)]
        return fake, results


class ClassifyTest(OnlineTest):
    def test_instruction_is_byte_identical_in_every_call_per_lane(self):
        snippets = ["echo 1;", "$x = $_GET['a'];\n" * 500, "", "unserialize($_COOKIE['d']);"]
        models = set()
        for lane in config.LANES:
            fake, _ = self.classify_with(["none"] * len(snippets), snippets, lane)
            self.assertEqual(len(fake.calls), len(snippets))
            for call in fake.calls:
                system = call["messages"][0]
                self.assertEqual(system["role"], "system")
                self.assertEqual(system["content"].encode(), config.LANES[lane].instruction.encode())
                self.assertIs(system["content"], config.LANES[lane].instruction)
                # Nothing else that defines the task varies between calls.
                self.assertEqual(sorted(call), ["messages", "metadata", "model", "temperature"])
                self.assertEqual(len(call["messages"]), 2)
                models.add(call["model"])
        # Same model for every lane, so the instruction is the only difference.
        self.assertEqual(len(models), 1)

    def test_lanes_have_distinct_instructions(self):
        instructions = [lane.instruction for lane in config.LANES.values()]
        self.assertEqual(len(set(instructions)), len(instructions))

    def test_web_php_instruction_unchanged(self):
        self.assertEqual(
            config.LANES["web_php"].instruction,
            "You are a PHP security reviewer. Classify the snippet as one of: sql_injection, xss, "
            "hardcoded_secret, path_traversal, unsafe_deserialization, none. Reply with the label only.",
        )

    def test_snippet_is_truncated_and_session_id_sent(self):
        fake, _ = self.classify_with(["none"], ["A" * 5000])
        self.assertEqual(len(fake.calls[0]["messages"][1]["content"]), config.MAX_SNIPPET_CHARS)
        self.assertEqual(fake.calls[0]["metadata"], {"session_id": "session-0"})

    def test_store_false_sends_no_store_header_only_when_asked(self):
        fake = FakeClient(["none", "none"])
        with mock.patch.object(classifier, "make_client", return_value=fake):
            classifier.classify("a", "s", "web_php")
            classifier.classify("b", "s", "web_php", store=False)
        self.assertNotIn("extra_headers", fake.calls[0])
        self.assertEqual(fake.calls[1]["extra_headers"], {"x-middleware-store": "false"})
        # Task-defining fields are unchanged by the header.
        self.assertEqual(fake.calls[0]["messages"][0], fake.calls[1]["messages"][0])
        self.assertEqual(fake.calls[0]["model"], fake.calls[1]["model"])

    def test_gemini_route_omits_metadata_but_keeps_instruction(self):
        with mock.patch.dict(os.environ, {"MUBIT_BASE_URL": "https://api.mubit.ai/gemini/v1beta/openai"}):
            fake, _ = self.classify_with(["none", "none"], ["a", "b"])
        for call in fake.calls:
            self.assertEqual(sorted(call), ["messages", "model", "temperature"])
            self.assertIs(call["messages"][0]["content"], config.LANES["web_php"].instruction)

    def test_reply_is_normalized_and_request_id_returned(self):
        _, results = self.classify_with(["  SQL_Injection\n"], ["x"])
        self.assertEqual(results[0], ("sql_injection", "req-1"))

    def test_labels_are_validated_per_lane(self):
        _, results = self.classify_with(["prompt_injection"], ["x"], "web_php")
        self.assertEqual(results[0][0], "unparseable")
        _, results = self.classify_with(["Prompt_Injection"], ["x"], "ai_app")
        self.assertEqual(results[0][0], "prompt_injection")

    def test_invalid_reply_is_unparseable_not_none(self):
        _, results = self.classify_with(["The snippet looks like sql_injection", "safe"], ["x", "y"])
        self.assertEqual([r[0] for r in results], ["unparseable", "unparseable"])

    def test_retries_429_honouring_retry_after_at_most_twice(self):
        with mock.patch.object(classifier.time, "sleep") as sleep:
            fake, results = self.classify_with([rate_limited("3"), rate_limited("1"), "xss"], ["x"])
        self.assertEqual(results[0][0], "xss")
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [3.0, 1.0])

        with mock.patch.object(classifier.time, "sleep"):
            with self.assertRaises(openai.RateLimitError):
                self.classify_with([rate_limited("0")] * 3, ["x"])


class AnthropicRouteTest(OnlineTest):
    def setUp(self):
        super().setUp()
        patcher = mock.patch.dict(os.environ, {"MUBIT_BASE_URL": "https://api.mubit.ai/anthropic"})
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_calls(self, lane, snippets, store=True):
        fake = FakeAnthropic(["  Prompt_Injection\n"] * len(snippets))
        with mock.patch.object(classifier, "make_anthropic_client", return_value=fake):
            results = [classifier.classify(s, f"sess-{i}", lane, store=store) for i, s in enumerate(snippets)]
        return fake, results

    def test_native_messages_call_shape_is_constant_per_lane(self):
        self.assertTrue(config.anthropic_route())
        for lane in config.LANES:
            fake, _ = self.run_calls(lane, ["a", "b" * 3000, ""])
            for i, call in enumerate(fake.calls):
                self.assertEqual(sorted(call), ["max_tokens", "messages", "metadata", "model", "system"])
                self.assertIs(call["system"], config.LANES[lane].instruction)
                self.assertEqual(call["max_tokens"], config.reply_tokens())
                self.assertEqual(call["model"], "claude-haiku-4-5")
                self.assertEqual(call["metadata"], {"user_id": f"sess-{i}"})
                self.assertEqual([m["role"] for m in call["messages"]], ["user"])
                self.assertLessEqual(len(call["messages"][0]["content"]), config.MAX_SNIPPET_CHARS)

    def test_opus_gets_low_effort_and_room_to_think(self):
        with mock.patch.dict(os.environ, {"MUBIT_MODEL": "claude-opus-5-5"}):
            fake, _ = self.run_calls("web_php", ["a", "b"])
        for call in fake.calls:
            self.assertEqual(call["output_config"], {"effort": "low"})
            self.assertEqual(call["max_tokens"], config.THINKING_REPLY_TOKENS)
            self.assertNotIn("thinking", call)
            self.assertIs(call["system"], config.LANES["web_php"].instruction)

    def test_real_sdk_accepts_our_arguments(self):
        import inspect
        import anthropic
        params = inspect.signature(anthropic.Anthropic(api_key="x").messages.create).parameters
        for name in ("model", "max_tokens", "system", "messages", "metadata", "extra_headers", "output_config"):
            self.assertIn(name, params, name)

    def test_reply_label_request_id_and_usage(self):
        _, results = self.run_calls("ai_app", ["x"])
        self.assertEqual(results[0], ("prompt_injection", "areq-1"))
        ledger = json.loads((Path(self.tmp.name) / "spend.json").read_text())
        self.assertEqual(ledger["lanes"]["ai_app"]["input_tokens"], 120)

    def test_store_false_header_on_anthropic_route(self):
        fake, _ = self.run_calls("web_php", ["x"], store=False)
        self.assertEqual(fake.calls[0]["extra_headers"], {"x-middleware-store": "false"})

    def test_openai_format_path_is_not_the_anthropic_route(self):
        with mock.patch.dict(os.environ, {"MUBIT_BASE_URL": "https://api.mubit.ai/anthropic/v1"}):
            self.assertFalse(config.anthropic_route())


class SpendTest(OnlineTest):
    def test_usage_is_recorded_per_lane(self):
        self.classify_with(["none", "none"], ["a", "b"], "web_php")
        self.classify_with(["none"], ["c"], "ai_app")
        ledger = json.loads((Path(self.tmp.name) / "spend.json").read_text())
        self.assertEqual(ledger["lanes"]["web_php"]["calls"], 2)
        self.assertEqual(ledger["lanes"]["ai_app"]["calls"], 1)
        self.assertEqual(ledger["lanes"]["web_php"]["input_tokens"], 200)
        # Haiku 4.5: $1 in / $5 out per million tokens.
        self.assertAlmostEqual(ledger["lanes"]["ai_app"]["usd"], (100 * 1 + 4 * 5) / 1e6)
        self.assertAlmostEqual(ledger["total_usd"], 3 * (100 * 1 + 4 * 5) / 1e6)

    def test_cap_stops_before_the_call(self):
        with mock.patch.dict(os.environ, {"GUARD_BUDGET_USD": "0.0001"}):
            (Path(self.tmp.name) / "spend.json").write_text(json.dumps({"total_usd": 0.0001, "lanes": {}}))
            fake = FakeClient(["none"])
            with mock.patch.object(classifier, "make_client", return_value=fake):
                with self.assertRaises(spend.BudgetExceeded):
                    classifier.classify("x", "s", "web_php")
        self.assertEqual(fake.calls, [])

    def test_unknown_model_priced_conservatively(self):
        self.assertGreater(spend.cost(1000, 10, "some-unknown-model"), spend.cost(1000, 10, "claude-haiku-4-5"))


class LocalChecksTest(unittest.TestCase):
    def test_detects_and_redacts(self):
        cases = [
            "$k = 'sk_live_FAKE_EXAMPLE_0001';",
            "$k = 'sk-FAKEexample000000000000000000';",
            "'key' => 'AKIAFAKEEXAMPLE00001'",
            "$api_key = 'FAKE0000EXAMPLEKEY1111';",
            "'client_secret' => \"FAKEsecretEXAMPLEvalue00\"",
            'client = OpenAI(api_key="sk-FAKEexample000000000000000000000000")',
        ]
        for code in cases:
            label, redacted = local_checks.check(code)
            self.assertEqual(label, "hardcoded_secret", code)
            self.assertIn("[REDACTED]", redacted, code)
            self.assertNotIn("FAKE", redacted, code)

    def test_ignores_secret_references(self):
        for code in ['sm.get_secret_value(SecretId="analytics/warehouse-prod")',
                     "secret_name = 'projects/acme/secrets/db-password'",
                     'SECRET_ARN = "arn:aws:secretsmanager:eu-west-2:000000000000:secret:FAKE"',
                     'api_key_env = "ACME_PAYMENTS_API_KEY_VAR"']:
            self.assertIsNone(local_checks.check(code)[0], code)
        # A real secret next to a reference is still caught and redacted.
        label, redacted = local_checks.check('id_ref = "x"\nclient_secret = "FAKEsecretEXAMPLEvalue00"')
        self.assertEqual(label, "hardcoded_secret")
        self.assertNotIn("FAKEsecret", redacted)

    def test_ignores_env_lookups(self):
        self.assertEqual(local_checks.check("$k = getenv('STRIPE_SECRET_KEY');")[0], None)
        self.assertEqual(local_checks.check('key = os.environ["OPENAI_API_KEY"]')[0], None)


if __name__ == "__main__":
    unittest.main()
