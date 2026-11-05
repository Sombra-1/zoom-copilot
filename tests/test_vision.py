import unittest
import sys
from unittest import mock

import zoom_copilot as app
from copilot_core.vision_capture import CaptureController


class Surface:
    def __init__(self):
        self.visible = "normal"
    def state(self):
        return self.visible
    def withdraw(self):
        self.visible = "withdrawn"
    def deiconify(self):
        self.visible = "normal"
    def iconify(self):
        self.visible = "iconic"
    def after(self, delay, function):
        function()
    def winfo_exists(self):
        return True


class InlineDispatch:
    def post(self, function):
        function()
        return True


class VisionTests(unittest.TestCase):
    def setUp(self):
        self.root = Surface()
        self.raw = mock.Mock(return_value="image")
        self.capture = CaptureController(self.root, InlineDispatch(), self.raw)
        self.settings = {"vision_mode": "manual", "vision_target": "region"}
        self.surfaces = mock.patch("copilot_core.vision_capture.private_surfaces", return_value=[self.root])
        self.surfaces.start()

    def tearDown(self):
        self.surfaces.stop()

    def test_disabled_never_captures_or_calls_provider(self):
        with self.assertRaisesRegex(RuntimeError, "Vision is off"):
            self.capture.take({"vision_mode": "off"})
        self.raw.assert_not_called()
        for backend in ("codex", "claude", "ollama"):
            with mock.patch("copilot_core.codex_backend.SERVICE.answer") as provider:
                with self.assertRaisesRegex(RuntimeError, "Vision is off"):
                    app.ask_ai_vision("image", "context", {"backend": backend, "vision_mode": "off"})
                provider.assert_not_called()

    def test_region_is_required_and_never_falls_back_to_desktop(self):
        for region in (None, (4, 4, 1, 1), (1, 1, 1, 3)):
            with self.assertRaisesRegex(RuntimeError, "Select a screen region"):
                self.capture.take(self.settings, region)
        self.raw.assert_not_called()

    def test_fallback_hides_overlay_and_restores_after_success(self):
        def grab(region):
            self.assertEqual(self.root.state(), "withdrawn")
            self.assertEqual(region, (1, 2, 5, 8))
            return "clean-image"
        self.raw.side_effect = grab
        self.assertEqual(self.capture.take(self.settings, (1, 2, 5, 8)), "clean-image")
        self.assertEqual(self.root.state(), "normal")

    def test_capture_error_restores_overlay(self):
        self.raw.side_effect = RuntimeError("capture failure")
        with self.assertRaisesRegex(RuntimeError, "capture failure"):
            self.capture.take(self.settings, (1, 2, 5, 8))
        self.assertEqual(self.root.state(), "normal")

    def test_verified_capture_keeps_overlay_visible(self):
        self.capture.verified = True
        with mock.patch("copilot_core.vision_capture.is_excluded", return_value=True):
            self.capture.take(self.settings, (1, 2, 5, 8))
        self.assertEqual(self.root.state(), "normal")

    def test_current_screen_requires_explicit_target(self):
        self.capture.take(dict(self.settings, vision_target="screen"))
        self.raw.assert_called_once_with(None)

    def test_all_displays_requires_explicit_desktop_target(self):
        self.capture.take(dict(self.settings, vision_target="desktop"))
        self.raw.assert_called_once_with(None, all_screens=True)

    def test_pillow_all_display_capture_is_explicit(self):
        grab = mock.Mock()
        with mock.patch.multiple(app, _MSS_AVAILABLE=False, _PIL_AVAILABLE=True,
                                 _PIL_ImageGrab=grab, create=True):
            app.capture_screen(all_screens=True)
            grab.grab.assert_called_once_with(bbox=None, all_screens=True)

    def test_mss_distinguishes_primary_all_displays_and_selected_region(self):
        mss = mock.MagicMock()
        engine = mss.mss.return_value.__enter__.return_value
        combined = {"left": -1920, "top": 0, "width": 3840, "height": 1080}
        primary = {"left": 0, "top": 0, "width": 1920, "height": 1080}
        engine.monitors = [combined, primary]
        with mock.patch.multiple(app, _MSS_AVAILABLE=True, _mss=mss, create=True), \
                mock.patch.dict(sys.modules, {"PIL": mock.Mock()}):
            app.capture_screen(all_screens=True)
            engine.grab.assert_called_with(combined)
            app.capture_screen()
            engine.grab.assert_called_with(primary)
            app.capture_screen((10, 20, 110, 220))
            engine.grab.assert_called_with({"left": 10, "top": 20, "width": 100, "height": 200})

    def test_watch_captures_immediately_without_waiting_for_the_interval(self):
        generation = app._begin_screen_session()
        gui = mock.Mock()
        gui._active_token.return_value = lambda: True
        gui.analyze_screen.side_effect = lambda *a, **kw: app._end_screen_session()
        with mock.patch.object(app.time, "sleep") as sleep:
            app.screen_watch_loop({"screen_interval": 10}, gui, generation)
        gui.analyze_screen.assert_called_once()
        sleep.assert_not_called()

    def test_selected_window_uses_direct_capture_and_never_desktop(self):
        with mock.patch("copilot_core.vision_capture.capture_window", return_value="window") as window:
            self.assertEqual(self.capture.take(dict(self.settings, vision_target="window"), window=99), "window")
            self.assertEqual(window.call_args.args[0], 99)
        self.raw.assert_not_called()

    def test_cancelled_and_closed_requests_do_not_capture(self):
        with self.assertRaises(RuntimeError):
            self.capture.take(self.settings, (1, 2, 5, 8), active=lambda: False)
        self.capture.close()
        with self.assertRaises(RuntimeError):
            self.capture.take(self.settings, (1, 2, 5, 8))
        self.raw.assert_not_called()
