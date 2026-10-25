"""Hosted API and remote client hook tests (offline: regex stub, no network)."""
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SQLI = 'function getUser($c) {\n  return mysqli_query($c, "SELECT * FROM users WHERE id = " . $_GET["id"]);\n}'
WP_SQLI = ('add_action("wp_ajax_export", function () {\n  global $wpdb;\n'
           '  return $wpdb->get_results("SELECT * FROM t WHERE id = " . $_POST["id"]);\n});')
SAFE = '$st = $pdo->prepare("SELECT * FROM users WHERE id = ?");\n$st->execute([$id]);'


class ServerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        env = {"GUARD_OFFLINE": "1", "GUARD_API_KEYS": "k1,k2", "GUARD_STATE_DIR": self.tmp.name, "GUARD_SCOPE_DIR": "/",
               "GUARD_RATE_PER_MIN": "100"}
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)
        from fastapi.testclient import TestClient
        from server import app as server_app
        server_app._calls.clear()
        self.app = server_app
        self.client = TestClient(server_app.app)

    def scan(self, path, content, key="k1"):
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        return self.client.post("/v1/scan", json={"file_path": path, "content": content}, headers=headers)

    def test_requires_a_known_key(self):
        self.assertEqual(self.scan("/x/a.php", SQLI, key=None).status_code, 401)
        self.assertEqual(self.scan("/x/a.php", SQLI, key="nope").status_code, 401)

    def test_blocks_php_sqli_with_skill(self):
        r = self.scan("/x/a.php", SQLI).json()
        self.assertEqual(r["decision"], "block")
        self.assertEqual(r["findings"][0]["label"], "sql_injection")
        self.assertEqual(r["findings"][0]["skill"], "php-sql-injection")

    def test_wordpress_code_gets_wordpress_skill(self):
        r = self.scan("/site/wp-content/plugins/x/export.php", WP_SQLI).json()
        self.assertEqual(r["findings"][0]["skill"], "wordpress-request-to-query")

    def test_safe_and_unrouted_files_are_allowed(self):
        self.assertEqual(self.scan("/x/a.php", SAFE).json()["decision"], "allow")
        self.assertEqual(self.scan("/x/notes.txt", SQLI).json(), {"decision": "allow", "lanes": [], "findings": [], "errors": []})

    def test_never_reads_server_files_for_routing(self):
        # config.py exists on the server; an Edit naming it must not route via its contents.
        with mock.patch("pathlib.Path.read_text", side_effect=AssertionError("read server file")):
            r = self.scan(str(ROOT / "agent.py"), "def run(out):\n    exec(out)\n")
        self.assertEqual(r.status_code, 200)

    def test_rate_limit_per_key(self):
        with mock.patch.dict(os.environ, {"GUARD_RATE_PER_MIN": "2"}):
            codes = [self.scan("/x/a.php", SAFE).status_code for _ in range(3)]
        self.assertEqual(codes, [200, 200, 429])

    def test_skills_are_served_and_ids_are_checked(self):
        self.assertIn("wordpress-request-to-query", self.client.get("/v1/skills").json()["skills"])
        md = self.client.get("/v1/skills/wordpress-request-to-query")
        self.assertEqual(md.status_code, 200)
        self.assertIn("CVE-2024-27956", md.text)
        self.assertEqual(self.client.get("/v1/skills/..%2Fconfig").status_code, 404)
        self.assertEqual(self.client.get("/v1/skills/does-not-exist").status_code, 404)

    def test_every_mapped_skill_exists(self):
        from server.skills import SKILLS, list_skills
        self.assertTrue(set(SKILLS.values()) | {"wordpress-request-to-query"} <= set(list_skills()))


class _FakeGuard(BaseHTTPRequestHandler):
    requests = []
    reply = {"decision": "allow", "findings": []}
    status = 200

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _FakeGuard.requests.append((self.headers.get("Authorization"), body))
        out = json.dumps(_FakeGuard.reply).encode()
        self.send_response(_FakeGuard.status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *args):
        pass


class RemoteClientTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), _FakeGuard)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def run_client(self, payload, url=None, key="k1"):
        env = {**os.environ, "GUARD_URL": url or self.url, "GUARD_KEY": key}
        env.pop("GUARD_DISABLED", None)
        return subprocess.run([sys.executable, str(ROOT / "client" / "guard_remote.py")],
                              input=json.dumps(payload), capture_output=True, text=True, env=env, timeout=30)

    def setUp(self):
        _FakeGuard.requests.clear()
        _FakeGuard.status = 200
        _FakeGuard.reply = {"decision": "allow", "findings": []}

    def test_block_shows_label_and_skill_link(self):
        _FakeGuard.reply = {"decision": "block", "findings": [{
            "lane": "web_php", "label": "sql_injection", "fix_hint": "Use prepared statements.",
            "skill": "php-sql-injection", "skill_url": "/v1/skills/php-sql-injection"}]}
        r = self.run_client({"tool_name": "Write", "tool_input": {"file_path": "/p/a.php", "content": SQLI}})
        self.assertEqual(r.returncode, 2)
        self.assertIn("sql_injection", r.stderr)
        self.assertIn(f"{self.url}/v1/skills/php-sql-injection", r.stderr)
        self.assertEqual(_FakeGuard.requests[0][0], "Bearer k1")

    def test_secrets_blocked_locally_and_never_sent(self):
        r = self.run_client({"tool_name": "Write", "tool_input": {
            "file_path": "/p/pay.php", "content": "$s = new StripeClient('sk_live_FAKE_EXAMPLE_0001');"}})
        self.assertEqual(r.returncode, 2)
        self.assertEqual(_FakeGuard.requests, [])

    def test_allow_and_fail_open(self):
        _FakeGuard.reply = {"decision": "allow", "findings": []}
        ok = self.run_client({"tool_name": "Edit", "tool_input": {"file_path": "/p/a.php", "new_string": SAFE}})
        down = self.run_client({"tool_name": "Write", "tool_input": {"file_path": "/p/a.php", "content": SQLI}},
                               url="http://127.0.0.1:9")
        self.assertEqual((ok.returncode, down.returncode), (0, 0))
        self.assertEqual(ok.stdout, "")
        self.assertIn("NOT checked", json.loads(down.stdout)["systemMessage"])

    def test_key_with_en_dash_warns_instead_of_failing_silently(self):
        # What `sh -s – KEY` (an auto-corrected "--") used to save as the key.
        for key in ("\u2013", "\u2013vh_abc", "vh_abc def"):
            r = self.run_client({"tool_name": "Write", "tool_input": {"file_path": "/p/a.php", "content": SQLI}},
                                key=key)
            self.assertEqual(r.returncode, 0, key)
            message = json.loads(r.stdout)["systemMessage"]
            self.assertIn("NOT checked", message)
            self.assertIn("sh -s -- YOUR_KEY", message)
        self.assertEqual(_FakeGuard.requests, [])

    def test_quoted_key_in_config_is_unwrapped(self):
        r = self.run_client({"tool_name": "Write", "tool_input": {"file_path": "/p/a.php", "content": SAFE}},
                            key=' "k1" ')
        self.assertEqual((r.returncode, r.stdout), (0, ""))
        self.assertEqual(_FakeGuard.requests[0][0], "Bearer k1")

    def test_rejected_key_is_reported(self):
        _FakeGuard.status = 401
        r = self.run_client({"tool_name": "Write", "tool_input": {"file_path": "/p/a.php", "content": SQLI}})
        self.assertEqual(r.returncode, 0)
        self.assertIn("rejected your key", json.loads(r.stdout)["systemMessage"])


if __name__ == "__main__":
    unittest.main()


class InstallerTest(unittest.TestCase):
    def test_install_script_sets_up_project_and_key(self):
        import functools
        from http.server import SimpleHTTPRequestHandler
        from fastapi.testclient import TestClient

        handler = functools.partial(SimpleHTTPRequestHandler, directory=str(ROOT))
        handler.log_message = lambda *a: None
        files = HTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=files.serve_forever, daemon=True).start()
        url = f"http://127.0.0.1:{files.server_port}"
        try:
            with mock.patch.dict(os.environ, {"PUBLIC_URL": url, "GUARD_API_KEYS": "k"}):
                from server import app as server_app
                client = TestClient(server_app.app)
                script = client.get("/install").text
                self.assertIn(f'URL="{url}"', script)
                self.assertEqual(client.get("/client/guard_remote.py").text,
                                 (ROOT / "client" / "guard_remote.py").read_text())

            with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as home:
                Path(project, ".claude").mkdir()
                Path(project, ".claude", "settings.json").write_text('{"permissions": {"allow": ["Bash(ls)"]}}')
                env = {**os.environ, "HOME": home}
                for _ in range(2):  # running twice must not duplicate the hook
                    r = subprocess.run(["sh", "-s", "--", "vh_test_key"], input=script, cwd=project,
                                       capture_output=True, text=True, env=env, timeout=60)
                    self.assertEqual(r.returncode, 0, r.stderr)
                settings = json.loads(Path(project, ".claude", "settings.json").read_text())
                self.assertEqual(settings["permissions"], {"allow": ["Bash(ls)"]})
                self.assertEqual(len(settings["hooks"]["PreToolUse"]), 1)
                self.assertTrue(Path(project, ".claude", "guard_remote.py").exists())
                config = Path(home, ".config", "vulhawk", "config")
                self.assertEqual(config.read_text(), f"GUARD_URL={url}\nGUARD_KEY=vh_test_key\n")
                self.assertEqual(oct(config.stat().st_mode & 0o777), "0o600")

                r = subprocess.run(["sh", "-s", "\u2013", "vh_dash_key"], input=script, cwd=project,
                                   capture_output=True, text=True, env=env, timeout=60)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertEqual(config.read_text(), f"GUARD_URL={url}\nGUARD_KEY=vh_dash_key\n")

                r = subprocess.run(["sh", "-s", "--", "vh_\u2019bad"], input=script, cwd=project,
                                   capture_output=True, text=True, env=env, timeout=60)
                self.assertEqual(r.returncode, 1)
                self.assertIn("sh -s -- YOUR_KEY", r.stdout)
                self.assertEqual(config.read_text(), f"GUARD_URL={url}\nGUARD_KEY=vh_dash_key\n")
        finally:
            files.shutdown()

    def test_client_reads_installer_config(self):
        with tempfile.TemporaryDirectory() as home:
            cfg = Path(home, ".config", "vulhawk")
            cfg.mkdir(parents=True)
            (cfg / "config").write_text("GUARD_URL=http://127.0.0.1:9\nGUARD_KEY=vh_x\n")
            env = {k: v for k, v in os.environ.items() if k not in ("GUARD_URL", "GUARD_KEY")}
            env["HOME"] = home
            code = ("import sys; sys.path.insert(0, 'client'); import guard_remote as g; "
                    "print(g.settings())")
            out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, env=env)
            self.assertIn("('http://127.0.0.1:9', 'vh_x')", out.stdout)
