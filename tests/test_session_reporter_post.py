"""Runs the session-reporter's Step 6 script against a local server.

The script lives inside skills/session-reporter/SKILL.md as a
``python3 << 'PYEOF'`` block that the model fills in and runs. This test pulls
that block out, fills the placeholders the way the model would, points it at a
throwaway HTTP server on 127.0.0.1 and checks what arrives.

Run with: python3 tests/test_session_reporter_post.py
"""

import base64
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL = os.path.join(REPO_ROOT, "skills", "session-reporter", "SKILL.md")


def step6_script():
    with open(SKILL, encoding="utf-8") as f:
        text = f.read()
    step6 = text[text.index("## Step 6"):]
    match = re.search(r"python3 << 'PYEOF'\n(.*?)\nPYEOF", step6, re.S)
    if not match:
        raise AssertionError("Step 6 python block not found in SKILL.md")
    return match.group(1)


class _Handler(BaseHTTPRequestHandler):
    received = []

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        type(self).received.append((self.path, raw))
        body = json.dumps({"id": "fb-test-1"}).encode()
        self.send_response(201)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class _RejectHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        body = json.dumps({"error": "rejected by the test"}).encode()
        self.send_response(400)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class SessionReporterPost(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), _Handler)
        cls.host = "http://127.0.0.1:%d" % cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        _Handler.received.clear()
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def run_script(self, images_raw, macro_code="Set swApp = Application.SldWorks", host=None):
        script = step6_script()
        script = script.replace("<SESSION_ID from session context>", "sess-test")
        script = script.replace("${user_config.SW_KB_HOST}", host or self.host)
        script = script.replace(
            "    # <paste learner images entries here, one dict per image>\n",
            "".join("    %r,\n" % img for img in images_raw))
        script = script.replace('"""<FULL SOURCE CODE>"""', repr(macro_code))
        path = os.path.join(self.tmp.name, "post.py")
        with open(path, "w", encoding="utf-8") as f:
            f.write(script)
        env = dict(os.environ, NO_PROXY="127.0.0.1", no_proxy="127.0.0.1")
        return subprocess.run([sys.executable, path], capture_output=True,
                              env=env, timeout=60)

    def received_payload(self, proc):
        out = proc.stdout.decode("utf-8", "replace")
        err = proc.stderr.decode("utf-8", "replace")
        self.assertEqual(proc.returncode, 0, "script failed:\n" + out + err)
        self.assertIn("Feedback submitted. ID: fb-test-1", out)
        self.assertEqual(len(_Handler.received), 1)
        path, raw = _Handler.received[0]
        self.assertEqual(path, "/api/feedback")
        return json.loads(raw.decode("utf-8"))

    def test_small_payload_is_posted(self):
        payload = self.received_payload(self.run_script([]))
        self.assertEqual(payload["sessionId"], "sess-test")
        self.assertNotIn("images", payload)

    def test_payload_larger_than_one_command_line_argument(self):
        # One screenshot is easily a few hundred KB of base64. That is over
        # Windows' 32,767-character command line and Linux's 128 KiB limit
        # for a single argument, so it cannot travel as a `curl -d` argument.
        png = b"\x89PNG\r\n\x1a\n" + os.urandom(200 * 1024)
        image = {"filename": "view.png", "contentType": "image/png",
                 "dataBase64": base64.b64encode(png).decode()}
        payload = self.received_payload(self.run_script([image]))
        self.assertEqual(base64.b64decode(payload["images"][0]["dataBase64"]), png)

    def test_non_ascii_text_arrives_as_utf8(self):
        code = "' Ø10 hole at 45°, fillet ≥ 2 mm, قطعه\nSet swApp = Application.SldWorks"
        payload = self.received_payload(self.run_script([], macro_code=code))
        self.assertEqual(payload["macros"][0]["code"], code)

    def test_image_given_by_native_path_is_encoded(self):
        # With native Windows Python this is a path like E:\work\view.png,
        # which exists as given; only WSL needs it rewritten to /mnt/e/...
        png = b"\x89PNG\r\n\x1a\n" + b"x" * 64
        path = os.path.join(self.tmp.name, "view.png")
        with open(path, "wb") as f:
            f.write(png)
        image = {"filename": "view.png", "contentType": "image/png", "path": path}
        payload = self.received_payload(self.run_script([image]))
        self.assertIn("images", payload, "image was dropped")
        self.assertEqual(base64.b64decode(payload["images"][0]["dataBase64"]), png)

    def test_a_missing_first_entry_does_not_block_a_later_usable_one(self):
        # A view.png that cannot be read must not reserve the name for the usable
        # view.png that follows it (#6).
        png = b"\x89PNG\r\n\x1a\n" + b"y" * 16
        missing = {"filename": "view.png",
                   "path": os.path.join(self.tmp.name, "missing-fixture.png")}
        usable = {"filename": "view.png", "contentType": "image/png",
                  "dataBase64": base64.b64encode(png).decode()}
        payload = self.received_payload(self.run_script([missing, usable]))
        self.assertEqual(len(payload.get("images", [])), 1, payload)
        self.assertEqual(base64.b64decode(payload["images"][0]["dataBase64"]), png)

    def test_a_same_name_entry_that_cannot_be_read_is_skipped(self):
        # A directory is not readable as an image, so encode_image() gives no data.
        unreadable = {"filename": "view.png", "path": self.tmp.name}
        usable = {"filename": "view.png", "contentType": "image/png",
                  "dataBase64": "Zml4dHVyZQ=="}
        payload = self.received_payload(self.run_script([unreadable, usable]))
        self.assertEqual(len(payload.get("images", [])), 1, payload)
        self.assertEqual(payload["images"][0]["dataBase64"], "Zml4dHVyZQ==")

    def test_two_usable_entries_with_the_same_name_keep_the_first(self):
        first = {"filename": "view.png", "contentType": "image/png", "dataBase64": "Zmlyc3Q="}
        second = {"filename": "view.png", "contentType": "image/png", "dataBase64": "c2Vjb25k"}
        payload = self.received_payload(self.run_script([first, second]))
        self.assertEqual(len(payload.get("images", [])), 1, payload)
        self.assertEqual(payload["images"][0]["dataBase64"], "Zmlyc3Q=")

    def test_a_rejected_submission_exits_nonzero(self):
        server = HTTPServer(("127.0.0.1", 0), _RejectHandler)
        host = "http://127.0.0.1:%d" % server.server_address[1]
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            proc = self.run_script([], host=host)
        finally:
            server.shutdown()
            server.server_close()

        out = proc.stdout.decode("utf-8", "replace")
        err = proc.stderr.decode("utf-8", "replace")
        self.assertNotEqual(proc.returncode, 0, out + err)
        self.assertIn("Feedback rejected (400)", out)
        self.assertIn("Feedback was not submitted.", err)

    def test_exhausted_retries_exit_nonzero(self):
        # A port nothing listens on: curl cannot connect, so every attempt
        # fails and the command must report that instead of exiting 0.
        probe = socket.socket()
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
        probe.close()

        proc = self.run_script([], host="http://127.0.0.1:%d" % port)

        out = proc.stdout.decode("utf-8", "replace")
        err = proc.stderr.decode("utf-8", "replace")
        self.assertNotEqual(proc.returncode, 0, out + err)
        self.assertEqual(out.count("failed ("), 3, out)
        self.assertIn("Attempt 3 failed (", out)
        self.assertNotIn("Retrying", out.split("Attempt 3")[-1])
        self.assertIn("Feedback was not submitted.", err)


if __name__ == "__main__":
    unittest.main(verbosity=2)
