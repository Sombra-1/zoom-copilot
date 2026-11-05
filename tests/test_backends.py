import json
import unittest
from unittest import mock

import zoom_copilot as app
from copilot_core.backends import backend_is_local
from copilot_core.codex_client import Cancelled


class BackendRegressionTests(unittest.TestCase):
    def setUp(self):
        self.messages = [{"role": "user", "content": "[TRANSCRIPT] A decision"}]

    def test_legacy_cloud_provider_payloads_are_preserved(self):
        replies = {"groq": {"choices": [{"message": {"content": "reply"}}]},
                   "claude": {"content": [{"text": "reply"}]},
                   "ollama": {"message": {"content": "reply"}}}
        for name, result in replies.items():
            settings = app._coerce_settings({"backend": name})
            response = mock.Mock()
            response.json.return_value = result
            with self.subTest(backend=name), mock.patch.object(app.requests, "post", return_value=response) as post:
                self.assertEqual(app.ask_ai(self.messages, settings), "reply")
                payload = post.call_args.kwargs["json"]
                self.assertEqual(payload["messages"][-1], self.messages[-1])
                self.assertNotIn("outputSchema", payload)

    def test_builtin_backend_uses_local_ollama(self):
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps({"message": {"content": "local"}}).encode()
        with mock.patch("urllib.request.urlopen", return_value=response) as call:
            self.assertEqual(app.ask_ai(self.messages, app._default_settings()), "local")
            self.assertTrue(call.call_args.args[0].full_url.startswith("http://localhost:11434"))

    def test_demo_notes_and_no_transcript_notes_do_not_require_cloud(self):
        settings = app._coerce_settings({"backend": "demo"})
        self.assertIn("No transcript", app.ask_meeting_notes([], settings))
        with mock.patch("time.sleep"):
            self.assertIn("## Decisions", app.ask_meeting_notes(["hello"], settings))

    def test_settings_migration_is_private_by_default(self):
        for name in app.BACKEND_CHOICES:
            settings = app._coerce_settings({"backend": name})
            self.assertEqual(settings["backend"], name)
            self.assertEqual(settings["vision_mode"], "off")
            self.assertEqual(settings["vision_target"], "region")
            self.assertFalse(settings["developer_mode"])
        settings = app._coerce_settings({"vision_mode": "bad", "vision_target": "all-monitors",
                                        "answer_detail": "bad", "codex_timeout": 9999,
                                        "answer_font_size": 80, "developer_mode": "false"})
        self.assertEqual(settings["vision_mode"], "off")
        self.assertEqual(settings["vision_target"], "region")
        self.assertEqual(settings["answer_detail"], "compact")
        self.assertEqual(settings["codex_timeout"], 300)
        self.assertEqual(settings["answer_font_size"], 24)
        self.assertFalse(settings["developer_mode"])

    def test_unknown_backend_is_reported(self):
        with self.assertRaisesRegex(ValueError, "Unknown backend"):
            app.ask_ai([], {"backend": "unknown"})

    def test_ollama_privacy_follows_actual_host(self):
        for host in ("http://localhost:11434", "http://127.0.0.1:11434", "http://[::1]:11434"):
            self.assertTrue(backend_is_local({"backend": "ollama", "ollama_host": host}))
        for host in ("https://example.com", "http://192.168.1.5:11434", "http://localhost.example.com", "invalid"):
            settings = {"backend": "ollama", "ollama_host": host, "transcription": "local"}
            self.assertFalse(backend_is_local(settings))
            self.assertNotEqual(app.privacy_mode_label(settings)[0], "LOCAL-FIRST")

    def test_cancelled_legacy_vision_is_rejected_before_network(self):
        with mock.patch.object(app.requests, "post") as post:
            with self.assertRaises(Cancelled):
                app.ask_ai_vision("image", "context", {"backend": "claude", "vision_mode": "manual"}, active=lambda: False)
            post.assert_not_called()
