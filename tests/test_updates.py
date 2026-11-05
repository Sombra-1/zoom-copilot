"""Release comparison, bounded networking, offline recovery and notification lifecycle."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import requests
import zoom_copilot as app
from copilot_core.updates import UpdateChecker, fetch_latest, version_tuple, API_URL, RELEASES_URL
from copilot_core.version import APP_VERSION


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = Path(self.folder.name) / "updates.json"
        self.root = mock.Mock()
        self.checker = UpdateChecker(self.root, lambda: None, self.path, enabled=False, clock=lambda: 100000)

    def tearDown(self):
        self.checker.close()
        self.folder.cleanup()

    def response(self, data=None, chunks=None, status=200):
        response = mock.Mock(status_code=status)
        response.__enter__ = mock.Mock(return_value=response)
        response.__exit__ = mock.Mock(return_value=False)
        response.iter_content.return_value = chunks or [json.dumps(data).encode()]
        return response

    def test_versions_compare_numerically_and_reject_unstable_tags(self):
        self.assertGreater(version_tuple("v2.10.0"), version_tuple("2.9.9"))
        for value in (None, 123, "v2.0.0-rc1", "3", "999999.0.0", "https://bad", "2.0.0\n"):
            self.assertIsNone(version_tuple(value))
        self.checker.latest = APP_VERSION
        self.assertFalse(self.checker.available)
        self.checker.latest = "1.0.0"
        self.assertFalse(self.checker.available)
        self.checker.latest = "99.0.0"
        self.assertTrue(self.checker.available)

    def test_public_check_has_timeout_size_bound_and_no_credentials(self):
        response = self.response({"tag_name": "v2.1.0", "draft": False, "prerelease": False})
        with mock.patch("copilot_core.updates.requests.get", return_value=response) as get:
            self.assertEqual(fetch_latest(), "2.1.0")
        self.assertEqual(get.call_args.args, (API_URL,))
        options = get.call_args.kwargs
        self.assertEqual(options["timeout"], (4, 8))
        self.assertFalse(options["allow_redirects"])
        self.assertNotIn("Authorization", options["headers"])
        self.assertNotIn("params", options)
        self.assertNotIn("data", options)
        with mock.patch("copilot_core.updates.requests.get", return_value=self.response(chunks=[b"x" * 65537])):
            with self.assertRaises(ValueError):
                fetch_latest()

    def test_malformed_prerelease_and_redirect_responses_are_rejected(self):
        for data in ([], {}, {"tag_name": "2.1.0", "draft": True, "prerelease": False},
                     {"tag_name": "2.1.0-rc1", "draft": False, "prerelease": True}):
            with mock.patch("copilot_core.updates.requests.get", return_value=self.response(data)):
                with self.assertRaises(ValueError):
                    fetch_latest()
        with mock.patch("copilot_core.updates.requests.get", return_value=self.response(status=302)):
            with self.assertRaises(ValueError):
                fetch_latest()

    def test_success_cache_and_per_version_dismissal_survive_restart(self):
        self.checker.complete("2.1.0", False)
        self.checker.dismiss()
        other = UpdateChecker(self.root, lambda: None, self.path, enabled=False, clock=lambda: 100100)
        self.assertEqual(other.dismissed, "2.1.0")
        with mock.patch("copilot_core.updates.fetch_latest") as fetch:
            other.check()
            fetch.assert_not_called()
        other.complete("2.2.0", False)
        self.assertNotEqual(other.latest, other.dismissed)
        other.close()

    def test_offline_request_is_dispatched_and_late_result_ignored(self):
        posts = []
        self.root._dispatcher.post.side_effect = posts.append
        # Execute the worker synchronously to verify the callback boundary.
        with mock.patch("copilot_core.updates.threading.Thread") as thread, \
                mock.patch("copilot_core.updates.fetch_latest", side_effect=requests.Timeout):
            thread.side_effect = lambda **kw: mock.Mock(start=kw["target"])
            self.checker.check(manual=True)
        self.assertTrue(self.checker.busy)
        self.assertEqual(len(posts), 1)
        posts[0]()
        self.assertFalse(self.checker.busy)
        self.assertIn("Offline", self.checker.message)
        self.checker.close()
        self.checker.complete("99.0.0", True)
        self.assertEqual(self.checker.latest, "")

    def test_manual_check_ignores_cache_and_restores_dismissed_release(self):
        self.checker.complete("2.1.0", False)
        self.checker.dismiss()
        self.root._dispatcher.post.side_effect = lambda callback: callback()
        with mock.patch("copilot_core.updates.threading.Thread") as thread, \
                mock.patch("copilot_core.updates.fetch_latest", return_value="2.1.0"):
            thread.side_effect = lambda **kw: mock.Mock(start=kw["target"])
            self.checker.check(manual=True)
        self.assertEqual(self.checker.dismissed, "")
        self.assertTrue(self.checker.available)

    def test_broken_cache_and_unwritable_state_are_nonfatal(self):
        self.path.write_text('{"checked": NaN, "latest": [1], "dismissed": true}')
        other = UpdateChecker(self.root, lambda: None, self.path, enabled=False)
        self.assertEqual(other.checked, 0)
        self.assertFalse(other.available)
        other.path = self.path / "not-a-directory.json"
        other.complete("2.1.0", False)
        other.close()

    def test_update_opens_only_fixed_project_release_url(self):
        with mock.patch("copilot_core.updates.webbrowser.open", return_value=True) as browser:
            self.checker.open_release()
            browser.assert_called_once_with(RELEASES_URL, new=2)

    def test_real_ui_notice_versions_dismissal_and_minimum_workspace(self):
        with mock.patch.object(app, "load_settings", side_effect=lambda: dict(app._default_settings(), backend="demo")), \
                mock.patch("copilot_core.vision_capture.CaptureController.probe", return_value=False):
            gui = app.App(support_state_file=Path(self.folder.name) / "support.json", check_updates=False)
            try:
                gui._updates.complete("2.1.0", False)
                gui.root.update()
                self.assertIn(APP_VERSION, gui.current._update_label.cget("text"))
                self.assertTrue(gui.current._update_strip.winfo_ismapped())
                gui._launch(dict(app._default_settings(), backend="demo"))
                gui.root.geometry("680x560")
                gui._community.usage.seconds = 10800
                gui._community.sync()
                gui.root.update()
                self.assertTrue(gui.current._update_strip.winfo_ismapped())
                self.assertTrue(gui.current._composer_send.winfo_ismapped())
                gui._updates.dismiss()
                gui.root.update()
                self.assertFalse(gui.current._update_strip.winfo_ismapped())
                gui._show_setup()
                gui.root.update()
                self.assertFalse(gui.current._update_strip.winfo_ismapped())
            finally:
                gui._quit()
