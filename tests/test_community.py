"""Support interactions and cumulative usage, without opening real websites."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import zoom_copilot as app
from copilot_core.community import UsageTracker, CommunitySupport, load_links, open_link, PROJECT_URL


class Clock:
    value = 0
    def __call__(self):
        return self.value
    def advance(self, seconds):
        self.value += seconds


class UsageTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = Path(self.folder.name) / "usage.json"
        self.clock = Clock()
        self.usage = UsageTracker(self.path, self.clock)
    def tearDown(self):
        self.folder.cleanup()
    def use(self, seconds):
        self.usage.tick(True)
        for _ in range(seconds // 10):
            self.clock.advance(10)
            self.usage.tick(True)
    def test_reminder_is_due_only_after_three_hours(self):
        self.use(10790)
        self.assertFalse(self.usage.due)
        self.use(10)
        self.assertTrue(self.usage.due)
    def test_usage_accumulates_across_launches(self):
        self.use(5400)
        self.usage.close()
        self.usage = UsageTracker(self.path, self.clock)
        self.use(5400)
        self.assertTrue(self.usage.due)
    def test_setup_idle_and_long_sleep_do_not_add_usage(self):
        self.clock.advance(100)
        self.usage.tick(True)
        self.clock.advance(10800)
        self.usage.tick(True)
        self.assertEqual(self.usage.seconds, 0)
        self.assertFalse(self.usage.due)
    def test_dismissal_persists_and_stops_collection(self):
        self.use(10800)
        self.usage.dismiss()
        self.usage = UsageTracker(self.path, self.clock)
        self.assertFalse(self.usage.due)
        self.assertTrue(self.usage.dismissed)
        self.assertEqual(set(json.loads(self.path.read_text())),
                         {"usage_seconds", "reminder_dismissed", "reminder_shown"})
    def test_invitation_is_shown_only_once_even_without_dismissal(self):
        self.use(10800)
        self.usage.mark_shown()
        self.usage = UsageTracker(self.path, self.clock)
        self.assertFalse(self.usage.due)
        self.assertTrue(self.usage.shown)
        self.assertFalse(self.usage.dismissed)
    def test_corrupt_usage_state_is_recoverable(self):
        self.path.write_text('{"usage_seconds": NaN, "reminder_dismissed": "yes"}')
        usage = UsageTracker(self.path, self.clock)
        self.assertEqual(usage.seconds, 0)
        self.assertFalse(usage.dismissed)
    def test_storage_failure_does_not_interrupt_the_app(self):
        self.path.write_text("not a directory")
        self.usage = UsageTracker(self.path / "usage.json", self.clock)
        self.use(60)
        self.usage.dismiss()
        self.assertTrue(self.usage.dismissed)


class SupportTests(unittest.TestCase):
    def test_donation_link_is_optional_and_urls_are_validated(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "support.json"
            path.write_text(json.dumps({"repository_url": "https://github.com.evil/repo",
                                        "donation_url": "javascript:bad()"}))
            self.assertEqual(load_links(folder), {"repository_url": PROJECT_URL, "donation_url": ""})
            path.write_text(json.dumps({"donation_url": "https://ko-fi.com/example"}))
            self.assertEqual(load_links(folder)["donation_url"], "https://ko-fi.com/example")
    def test_unconfigured_donation_shows_coming_soon(self):
        with mock.patch("copilot_core.community.messagebox.showinfo") as message, \
                mock.patch("copilot_core.community.webbrowser.open") as browser:
            self.assertFalse(open_link(None, "donate", {"donation_url": ""}))
            message.assert_called_once()
            browser.assert_not_called()
    def test_star_opens_exact_repository_in_the_users_browser(self):
        with mock.patch("copilot_core.community.webbrowser.open", return_value=True) as browser:
            self.assertTrue(open_link(None, "star", {"repository_url": PROJECT_URL}))
            browser.assert_called_once_with(PROJECT_URL, new=2)
    def test_support_opens_live_patreon_membership(self):
        with mock.patch("copilot_core.community.webbrowser.open", return_value=True) as browser:
            self.assertTrue(open_link(None, "donate", load_links()))
            browser.assert_called_once_with("https://www.patreon.com/cw/Sombra551/membership", new=2)
    def test_hidden_workspace_does_not_consume_invitation(self):
        with tempfile.TemporaryDirectory() as folder, mock.patch("copilot_core.support_ui.show_reminder") as show:
            root, view = mock.Mock(), mock.Mock()
            root.state.return_value = "withdrawn"
            service = CommunitySupport(root, lambda: True, lambda: view, Path(folder) / "state.json")
            service.usage.seconds = 10800
            service.sync()
            self.assertFalse(service.usage.shown)
            show.assert_called_with(view, False)
            root.state.return_value = "normal"
            service.sync()
            self.assertTrue(service.usage.shown)
            show.assert_called_with(view, True)
            service.sync()
            show.assert_called_with(view, True)
            service.close()
    def test_browser_failure_offers_a_copyable_link(self):
        with mock.patch("copilot_core.community.webbrowser.open", side_effect=OSError), \
                mock.patch("copilot_core.community.messagebox.showinfo") as message:
            self.assertFalse(open_link(None, "star", {"repository_url": PROJECT_URL}))
            self.assertIn(PROJECT_URL, message.call_args.args[1])
    def test_service_timer_is_cancelled_on_shutdown(self):
        with tempfile.TemporaryDirectory() as folder:
            root = mock.Mock()
            service = CommunitySupport(root, lambda: False, lambda: None, Path(folder) / "state.json")
            service.close()
            service.close()
            root.after_cancel.assert_called_once()
    def test_banner_buttons_and_dismissal_work_without_interrupting_workspace(self):
        with tempfile.TemporaryDirectory() as folder, \
                mock.patch.object(app, "load_settings", side_effect=lambda: dict(app._default_settings(), backend="demo")), \
                mock.patch("copilot_core.vision_capture.CaptureController.probe", return_value=False):
            gui = app.App(support_state_file=Path(folder) / "usage.json", check_updates=False)
            try:
                gui._launch(dict(app._default_settings(), backend="demo"))
                gui.root.update()
                gui._community.usage.seconds = 10800
                gui._community.sync()
                gui.root.update()
                screen = gui.current
                self.assertTrue(screen._support_dismiss.winfo_ismapped())
                screen._support_dismiss.invoke()
                gui.root.update()
                self.assertFalse(screen._support_dismiss.winfo_ismapped())
                self.assertTrue(gui._community.usage.dismissed)
                with mock.patch("copilot_core.community.webbrowser.open", return_value=True) as browser:
                    screen._support_star.invoke()
                    browser.assert_called_once_with(PROJECT_URL, new=2)
            finally:
                gui._quit()
