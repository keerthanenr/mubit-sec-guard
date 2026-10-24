"""Offline hook tests: pipe fake PreToolUse payloads to guard_hook.py on stdin."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / "guard_hook.py"

SQLI = 'function getUser($conn) {\n    $id = $_GET["id"];\n    return mysqli_query($conn, "SELECT * FROM users WHERE id = " . $id);\n}'
SAFE = 'function getUser(PDO $db) {\n    $stmt = $db->prepare("SELECT * FROM users WHERE id = ?");\n    $stmt->execute([$_GET["id"]]);\n    return $stmt->fetch();\n}'
SECRET = "$stripe = new \\Stripe\\StripeClient('sk_live_FAKE_EXAMPLE_0001');"
PY_INJECTION = (
    "import anthropic\n\n"
    "def reply(client, msg):\n"
    "    return client.messages.create(model=M, max_tokens=300,\n"
    "        system=f\"You are a bot. User says: {msg}\",\n"
    "        messages=[{\"role\": \"user\", \"content\": \"hi\"}])\n"
)
PY_PLAIN = "def add(a, b):\n    return eval(a) + b\n"


def payload(tool, file_path, **tool_input):
    return {
        "session_id": "test-session",
        "hook_event_name": "PreToolUse",
        "tool_name": tool,
        "tool_input": {"file_path": file_path, **tool_input},
    }


class HookTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state_dir = Path(self.tmp.name)
        self.env = {
            **os.environ,
            "GUARD_OFFLINE": "1",
            "GUARD_STATE_DIR": str(self.state_dir),
            # Never the real key, and an unreachable endpoint, in case anything tries the network.
            "MUBIT_API_KEY": "test-not-a-key",
            "MUBIT_BASE_URL": "http://127.0.0.1:9/v1",
            # Most tests use made-up /proj paths, so scan everything; scoping has its own test.
            "GUARD_SCOPE_DIR": "/",
            # Empty, not unset: config.load_env() would otherwise pick up GUARD_MODE from .env.
            "GUARD_MODE": "",
        }
        self.env.pop("GUARD_DISABLED", None)

    def tearDown(self):
        self.tmp.cleanup()

    def run_hook(self, data, **env):
        return subprocess.run(
            [sys.executable, str(HOOK)],
            input=json.dumps(data),
            capture_output=True,
            text=True,
            env={**self.env, **env},
            timeout=30,
        )

    def findings(self):
        path = self.state_dir / "findings.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def test_a_php_sql_injection_blocks(self):
        result = self.run_hook(payload("Write", "/proj/login.php", content=SQLI))
        self.assertEqual(result.returncode, 2)
        self.assertIn("guard: sql_injection in /proj/login.php (web_php)", result.stderr)
        self.assertIn("prepared statements", result.stderr)

    def test_b_safe_php_allows(self):
        result = self.run_hook(payload("Write", "/proj/login.php", content=SAFE))
        self.assertEqual(result.returncode, 0)
        self.assertEqual(self.findings()[-1]["decision"], "allow")

    def test_c_non_source_file_allows(self):
        result = self.run_hook(payload("Write", "/proj/notes.txt", content=SQLI))
        self.assertEqual(result.returncode, 0)
        self.assertEqual(self.findings(), [])

    def test_d_fake_secret_blocks_without_network(self):
        # Offline stub disabled: if the hook reached the classifier it would try the
        # unreachable endpoint, fail open and exit 0. Exit 2 proves the local check caught it.
        result = self.run_hook(payload("Write", "/proj/pay.php", content=SECRET), GUARD_OFFLINE="0")
        self.assertEqual(result.returncode, 2)
        self.assertIn("hardcoded_secret", result.stderr)
        entry = self.findings()[-1]
        self.assertIsNone(entry["request_id"])
        self.assertNotIn("sk_live_FAKE_EXAMPLE_0001", entry["snippet"])
        self.assertIn("[REDACTED]", entry["snippet"])

    def test_e_fourth_block_on_same_file_is_allowed(self):
        data = payload("Edit", "/proj/login.php", old_string="x", new_string=SQLI)
        codes = [self.run_hook(data).returncode for _ in range(4)]
        self.assertEqual(codes, [2, 2, 2, 0])
        self.assertEqual(self.findings()[-1]["decision"], "allowed_by_cap")

    def test_f_guard_disabled_allows_everything(self):
        result = self.run_hook(payload("Write", "/proj/login.php", content=SQLI), GUARD_DISABLED="1")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(self.findings(), [])

    def test_multiedit_new_strings_are_checked(self):
        data = payload("MultiEdit", "/proj/a.php", edits=[
            {"old_string": "a", "new_string": "$x = 1;"},
            {"old_string": "b", "new_string": SQLI},
        ])
        self.assertEqual(self.run_hook(data).returncode, 2)

    def test_ai_app_lane_blocks_prompt_injection(self):
        result = self.run_hook(payload("Write", "/proj/bot.py", content=PY_INJECTION))
        self.assertEqual(result.returncode, 2)
        self.assertIn("prompt_injection", result.stderr)
        self.assertIn("(ai_app)", result.stderr)
        self.assertEqual(self.findings()[-1]["lane"], "ai_app")

    def test_plain_source_goes_to_generic_lane(self):
        result = self.run_hook(payload("Write", "/proj/util.py", content=PY_PLAIN))
        self.assertEqual(result.returncode, 2)
        self.assertIn("code_injection", result.stderr)
        self.assertIn("(generic)", result.stderr)

    def test_non_source_file_is_ignored(self):
        result = self.run_hook(payload("Write", "/proj/notes.md", content=PY_PLAIN))
        self.assertEqual(result.returncode, 0)
        self.assertEqual(self.findings(), [])

    def test_python_edit_routed_by_imports_in_existing_file(self):
        target = self.state_dir / "agent.py"
        target.write_text("from openai import OpenAI\n")
        data = payload("Edit", str(target), old_string="x",
                       new_string="def run(out):\n    exec(out.choices[0].message.content)\n")
        self.assertEqual(self.run_hook(data).returncode, 2)

    def test_budget_cap_fails_open_without_calling(self):
        result = self.run_hook(payload("Write", "/proj/login.php", content=SQLI),
                               GUARD_OFFLINE="0", GUARD_BUDGET_USD="0")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(self.findings()[-1]["label"], "budget_exceeded")

    def test_hook_only_scans_inside_scope_dir(self):
        scope = self.state_dir / "demo-app"
        env = {"GUARD_SCOPE_DIR": str(scope)}
        outside = self.run_hook(payload("Write", str(self.state_dir / "seed.php"), content=SQLI), **env)
        inside = self.run_hook(payload("Write", str(scope / "login.php"), content=SQLI), **env)
        sneaky = self.run_hook(payload("Write", str(scope / ".." / "x.php"), content=SQLI), **env)
        self.assertEqual((outside.returncode, inside.returncode, sneaky.returncode), (0, 2, 0))

    def test_default_scope_is_demo_app_in_project(self):
        env = {"GUARD_SCOPE_DIR": "", "CLAUDE_PROJECT_DIR": str(self.state_dir)}
        own_script = self.run_hook(payload("Write", str(self.state_dir / "x.php"), content=SQLI), **env)
        demo = self.run_hook(payload("Write", str(self.state_dir / "demo-app" / "x.php"), content=SQLI), **env)
        self.assertEqual((own_script.returncode, demo.returncode), (0, 2))

    def test_routes_to_every_matching_lane(self):
        import guard_hook
        cases = {
            "a.php": ("echo 1;", ["web_php"]),
            "b.py": ("import torch\nmodel = torch.load(p)\n", ["ml_code"]),
            "c.py": ("from langchain_community.vectorstores import Chroma\n", ["ai_app", "rag_app"]),
            "d.py": ("from langgraph.graph import StateGraph\n", ["agent_app"]),
            "e.py": ("import pandas as pd\n", ["data_science"]),
            "f.ipynb": ("x = 1", ["data_science"]),
            "g.py": ("import os\n", ["generic"]),
            "cli.go": ("package main\n", ["generic"]),
            "Main.java": ("class Main {}\n", ["generic"]),
            "run.sh": ("echo hi\n", ["generic"]),
            "util.js": ("const fs = require('fs')\n", ["generic"]),
            "api.js": ("const express = require('express')\n", ["web_app", "api_security"]),
            "routes.ts": ("import { Router } from 'express'\n", ["web_app", "api_security"]),
            "README.md": ("eval(x)\n", []),
            "server.py": ("from mcp.server.fastmcp import FastMCP\n", ["agent_app", "mcp_server"]),
            ".mcp.json": ('{"mcpServers": {}}', ["mcp_server"]),
            "main.tf": ('resource "aws_s3_bucket" "b" {}', ["data_pipeline"]),
            "grants.sql": ("GRANT SELECT ON t TO r;", ["data_pipeline"]),
            "etl.py": ("import boto3\nimport pandas as pd\n", ["data_science", "data_pipeline"]),
            "bq.py": ("from google.cloud import bigquery\n", ["data_pipeline"]),
            "notes.json": ('{"a": 1}', []),
            "app.py": ("from flask import Flask\n", ["web_app", "api_security"]),
            "server.ts": ("import express from 'express'\n", ["web_app", "api_security"]),
            ".github/workflows/ci.yml": ("on: push\njobs:\n  b:\n    steps: []\n", ["cicd"]),
            ".gitlab-ci.yml": ("build:\n  script: make\n", ["cicd"]),
            "deploy.yaml": ("apiVersion: apps/v1\nkind: Deployment\n", ["k8s_iac"]),
            "settings.yaml": ("debug: true\n", []),
        }
        with mock.patch.dict(os.environ, {"GUARD_SCOPE_DIR": "/"}):
            for name, (code, lanes) in cases.items():
                self.assertEqual(guard_hook.route(f"/proj/{name}", code), lanes, name)

    def test_notebook_write_and_notebook_edit_are_checked(self):
        nb = json.dumps({"cells": [
            {"cell_type": "markdown", "source": ["# report"]},
            {"cell_type": "code", "source": ["df = pd.read_pickle(path)\n"]},
        ]})
        self.assertEqual(self.run_hook(payload("Write", "/proj/report.ipynb", content=nb)).returncode, 2)
        edit = {"session_id": "t", "tool_name": "NotebookEdit",
                "tool_input": {"notebook_path": "/proj/report2.ipynb", "new_source": "obj = pickle.load(f)"}}
        self.assertEqual(self.run_hook(edit).returncode, 2)
        self.assertEqual(self.findings()[-1]["lane"], "data_science")

    def test_mubit_error_fails_open(self):
        result = self.run_hook(payload("Write", "/proj/login.php", content=SQLI), GUARD_OFFLINE="0")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(self.findings()[-1]["decision"], "error")


    def test_warn_mode_allows_and_reports(self):
        result = self.run_hook(payload("Write", "/proj/login.php", content=SQLI), GUARD_MODE="warn")
        self.assertEqual(result.returncode, 0)
        out = json.loads(result.stdout)
        self.assertIn("sql_injection", out["systemMessage"])
        self.assertIn("sql_injection", out["hookSpecificOutput"]["additionalContext"])
        self.assertNotIn("permissionDecision", out["hookSpecificOutput"])
        self.assertEqual(self.findings()[-1]["decision"], "warn")

    def test_ask_mode_hands_decision_to_user(self):
        result = self.run_hook(payload("Write", "/proj/login.php", content=SQLI), GUARD_MODE="ask")
        self.assertEqual(result.returncode, 0)
        out = json.loads(result.stdout)["hookSpecificOutput"]
        self.assertEqual(out["permissionDecision"], "ask")
        self.assertIn("Use prepared statements", out["permissionDecisionReason"])
        self.assertEqual(self.findings()[-1]["decision"], "ask")

    def test_non_block_modes_print_nothing_for_safe_code(self):
        for mode in ("warn", "ask"):
            result = self.run_hook(payload("Write", "/proj/safe.php", content=SAFE), GUARD_MODE=mode)
            self.assertEqual((result.returncode, result.stdout), (0, ""), mode)

    def test_unknown_mode_falls_back_to_block(self):
        result = self.run_hook(payload("Write", "/proj/login.php", content=SQLI), GUARD_MODE="loud")
        self.assertEqual(result.returncode, 2)


if __name__ == "__main__":
    unittest.main()
