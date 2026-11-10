"""Offline widget construction/disclosure tests; no model or capture calls."""
import json
import threading
import tkinter as tk
import unittest
import gc
import time
from unittest import mock

import zoom_copilot as app
from copilot_core.answer_renderer import AnswerHud
from copilot_core.debug_panel import DebugPanel
from copilot_core.ui_dispatch import UiDispatcher
from copilot_core.ui_theme import destroy_root
from copilot_core import overlay_view, setup_view
from copilot_core.codex_backend import CodexStatus


class UiTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError:
            self.skipTest("Tk display unavailable")
        self.root.withdraw()
        self.root.update()
        self.root._dispatcher = UiDispatcher(self.root)
        self.math = mock.patch("copilot_core.math_renderer.MathRenderer.render", return_value=[])
        self.math.start()
        self.capture = mock.patch("copilot_core.vision_capture.CaptureController.probe", return_value=False)
        self.capture.start()

    def tearDown(self):
        if hasattr(self, "root"):
            self.root._dispatcher.close()
            destroy_root(self.root)
            self.math.stop()
            self.capture.stop()
            self.root = None
            gc.collect()

    def pump_until(self, predicate):
        deadline = time.monotonic() + 2
        while not predicate() and time.monotonic() < deadline:
            self.root.update()
            time.sleep(.01)
        self.assertTrue(predicate())

    def test_connection_and_workspace_do_not_require_unused_audio_credentials(self):
        settings = dict(app._default_settings(), backend="demo", transcription="groq", groq_key="")
        launched = []
        screen = app.SetupScreen(self.root, settings, launched.append)
        with mock.patch.object(app, "_call_ai_backend", return_value="OK") as call:
            screen._test()
            self.pump_until(lambda: screen._status.cget("text").startswith("Connected"))
            self.assertEqual(call.call_count, 1)
        with mock.patch.object(app, "save_settings"):
            screen._launch()
        self.assertEqual(len(launched), 1)
        screen.destroy()

    def test_audio_test_recovers_from_device_query_error(self):
        screen = app.SetupScreen(self.root, app._default_settings(), lambda _: None)
        main_thread = threading.get_ident()
        called_on = []

        def fail_query(_):
            called_on.append(threading.get_ident())
            raise OSError("Device disconnected")

        with mock.patch.object(app, "find_device", side_effect=fail_query):
            screen._mic_btn.invoke()
            self.pump_until(lambda: "Device disconnected" in screen._mic_status.cget("text")
                            and screen._mic_btn.cget("state") == "normal")
        self.assertEqual(len(called_on), 1)
        self.assertNotEqual(called_on[0], main_thread)
        screen.destroy()

    def test_setup_credentials_remain_visible_across_pages_and_bindings_are_cleaned(self):
        binding = self.root.bind("<MouseWheel>", lambda _: None, add="+")
        before = self.root.bind("<MouseWheel>").strip()
        screen = app.SetupScreen(self.root, dict(app._default_settings(), backend="demo"), lambda _: None)
        for name in screen._pages:
            setup_view.show_page(screen, name)
            self.root.update_idletasks()
            self.assertTrue(screen._groq_key_frame.grid_info())
            self.assertIs(screen._pages[name]._root(), self.root)
        calls = []
        worker = threading.Thread(target=lambda: screen._post(lambda: calls.append("stale")))
        worker.start()
        worker.join()
        screen.destroy()
        self.root._dispatcher._drain()
        self.assertEqual(calls, [])
        self.assertEqual(self.root.bind("<MouseWheel>").strip(), before)
        self.root.unbind("<MouseWheel>", binding)

    def test_overlay_destruction_preserves_other_listen_shortcuts(self):
        binding = self.root.bind("<Control-l>", lambda _: None, add="+")
        before = self.root.bind("<Control-l>").strip()
        overlay = app.OverlayScreen(self.root, app._default_settings(), lambda: None)
        overlay.destroy()
        self.assertEqual(self.root.bind("<Control-l>").strip(), before)
        self.root.unbind("<Control-l>", binding)

    def test_delayed_copy_feedback_is_cancelled_when_switching_views(self):
        overlay = app.OverlayScreen(self.root, app._default_settings(), lambda: None)
        overlay.clear()
        overlay._copy_last_ai()
        timers = set(overlay._ui_timers)
        self.assertTrue(timers)
        overlay.destroy()
        self.assertFalse(timers.intersection(self.root.tk.call("after", "info")))

    def test_consecutive_questions_do_not_include_placeholder_text(self):
        overlay = app.OverlayScreen(self.root, app._default_settings(), lambda: None)
        overlay.clear()
        with mock.patch.object(app, "ask_ai", return_value="Acknowledged.") as ask:
            for index, question in enumerate(("First question", "Second question"), 1):
                overlay._manual_entry.event_generate("<FocusIn>")
                overlay._manual_entry.insert("1.0", question)
                overlay._send_manual()
                self.pump_until(lambda: len(overlay.hud.answers) == index)
                self.assertFalse(overlay._input_has_placeholder)
                self.assertFalse(overlay._manual_entry.get("1.0", "end").strip())
                users = [m["content"] for m in ask.call_args.args[0] if m["role"] == "user"]
                self.assertEqual(users[-1], "[USER] " + question)
        overlay.destroy()

    def test_codex_status_can_retry_after_an_unexpected_startup_failure(self):
        screen = app.SetupScreen(self.root, dict(app._default_settings(), backend="demo"), lambda _: None)
        screen._vars["backend"].set("codex")
        with mock.patch.object(app.CODEX, "status", side_effect=RuntimeError("startup failure")):
            screen._check_codex()
            self.pump_until(lambda: not screen._cx_checking)
        self.assertIn("Refresh status", screen._cx_status.cget("text"))
        with mock.patch.object(app.CODEX, "status", return_value=CodexStatus(True, True, True)):
            screen._check_codex()
            self.pump_until(lambda: not screen._cx_checking)
        self.assertIn("Available: Yes", screen._cx_status.cget("text"))
        screen.destroy()

    def test_region_picker_timer_and_window_are_closed_when_switching_views(self):
        overlay = app.OverlayScreen(self.root, app._default_settings(), lambda: None)
        overlay._pick_region()
        timer = overlay._selector_after_id
        self.assertEqual(self.root.state(), "withdrawn")
        overlay.destroy()
        self.assertNotIn(timer, self.root.tk.call("after", "info"))
        self.assertNotEqual(self.root.state(), "withdrawn")
        overlay = app.OverlayScreen(self.root, app._default_settings(), lambda: None)
        with mock.patch.object(app, "RegionSelector", wraps=app.RegionSelector) as selector:
            overlay._pick_region()
            self.pump_until(lambda: getattr(overlay, "_region_selector", None) is not None)
            window = overlay._region_selector
            callback = selector.call_args.args[1]
            overlay.destroy()
            self.assertFalse(window.winfo_exists())
            # A result that arrives after destruction cannot mutate dead widgets.
            callback(10, 20, 200, 300)

    def test_codex_status_rechecks_model_edits_instead_of_showing_stale_results(self):
        screen = app.SetupScreen(self.root, dict(app._default_settings(), backend="demo"), lambda _: None)
        screen._vars["backend"].set("codex")
        release = threading.Event()
        checked = []
        def status(settings):
            checked.append(settings["codex_model"])
            if not settings["codex_model"]:
                release.wait(1)
                return CodexStatus(detail="Old model result")
            return CodexStatus(True, True, True, detail="Updated model checked")
        with mock.patch.object(app.CODEX, "status", side_effect=status):
            screen._check_codex()
            screen._vars["codex_model"].set("updated-model")
            release.set()
            self.pump_until(lambda: "Updated model checked" in screen._cx_status.cget("text"))
        self.assertEqual(checked, ["", "updated-model"])
        screen.destroy()

    def test_clear_stops_watch_and_disabled_controls_match_vision_mode(self):
        overlay = app.OverlayScreen(self.root, app._default_settings(), lambda: None)
        self.assertEqual(overlay._capture_now_btn.cget("state"), "disabled")
        self.assertEqual(overlay._screen_btn.cget("state"), "disabled")
        with mock.patch.object(app, "save_settings"):
            overlay._vision_mode.set("periodic")
            overlay._vision_changed()
        self.assertEqual(overlay._screen_btn.cget("state"), "normal")
        app._begin_screen_session()
        overlay._previous_screen = b"old image"
        overlay.clear()
        self.assertFalse(app._screen_watch_event.is_set())
        self.assertIsNone(overlay._previous_screen)
        self.assertEqual(overlay._screen_btn.cget("text"), "Watch")
        overlay.destroy()

    def test_small_window_keeps_answer_and_composer_accessible(self):
        overlay = app.OverlayScreen(self.root, app._default_settings(), lambda: None)
        scale = overlay._body._get_widget_scaling()
        self.root.geometry(f"{round(680 * scale)}x{round(560 * scale)}")
        self.root.deiconify()
        overlay_view.toggle_vision(overlay)
        self.root.update()
        self.assertEqual(overlay._layout_mode, "answer")
        self.assertGreaterEqual(overlay.hud.text.winfo_height(), 50 * scale)
        self.assertTrue(overlay._composer_send.winfo_ismapped())
        self.assertLess(overlay._composer_send.winfo_rooty() + overlay._composer_send.winfo_height(),
                        self.root.winfo_rooty() + self.root.winfo_height())
        overlay_view.toggle_focus(overlay)
        self.root.update()
        self.assertTrue(overlay.chat.winfo_ismapped())
        self.assertFalse(overlay.hud.winfo_ismapped())
        overlay_view.toggle_focus(overlay)
        overlay.append_message("ERROR", "A useful connection error", "error")
        self.root.update()
        self.assertTrue(overlay._error_btn.winfo_ismapped())
        overlay._error_btn.invoke()
        self.root.update()
        self.assertIn("A useful connection error", overlay.chat.get("1.0", "end"))
        self.assertTrue(overlay.chat.winfo_ismapped())
        for height in (600, 640, 680, 720, 740, 760):
            self.root.geometry(f"{round(680 * scale)}x{round(height * scale)}")
            self.root.update()
            mode = overlay._layout_mode
            overlay_view.adapt_layout(overlay)
            self.root.update()
            self.assertEqual(overlay._layout_mode, mode)
        self.root.geometry(f"{round(960 * scale)}x{round(650 * scale)}")
        self.root.update()
        self.assertEqual(overlay._layout_mode, "activity")
        overlay_view.toggle_vision(overlay)
        self.root.update()
        self.assertEqual(overlay._layout_mode, "split")
        self.assertTrue(overlay.hud.winfo_ismapped() and overlay.chat.winfo_ismapped())
        self.assertLess(overlay.hud.winfo_rootx(), overlay.chat.winfo_rootx())
        overlay_view.toggle_focus(overlay)
        self.root.update()
        self.assertFalse(overlay.chat.winfo_ismapped())
        self.assertEqual(overlay._focus_btn.cget("text"), "Exit focus")
        overlay.destroy()

    def test_pinned_answer_survives_history_limit(self):
        hud = AnswerHud(self.root, app._default_settings(), app.C, self.root._dispatcher)
        hud.add("Keep this answer")
        hud.pin()
        for index in range(55):
            hud.add("Later answer " + str(index))
        self.assertEqual(len(hud.answers), 50)
        self.assertIn("Keep this answer", hud.text.get("1.0", "end"))
        hud.destroy()

    def test_whole_screen_toggle_requires_no_window_or_region_picker(self):
        overlay = app.OverlayScreen(self.root, dict(app._default_settings(), backend="codex"), lambda: None)
        with mock.patch.object(app, "save_settings"), mock.patch.object(app, "screen_watch_loop") as loop, \
                mock.patch.object(app, "screen_capture_available", return_value=True), \
                mock.patch.object(overlay, "_pick_region") as region, mock.patch.object(overlay, "_pick_window") as window:
            overlay._set_desktop_watch(True)
            self.pump_until(lambda: loop.called)
            self.assertEqual(overlay.s["vision_target"], "desktop")
            self.assertEqual(overlay.s["vision_mode"], "periodic")
            self.assertTrue(overlay._desktop_watch.get())
            self.assertIn("All displays", overlay._vision_privacy.cget("text"))
            overlay._toggle_desktop_watch()
            self.assertEqual(overlay.s["vision_mode"], "off")
            self.assertFalse(app._screen_watch_event.is_set())
            self.assertFalse(overlay._desktop_watch.get())
            region.assert_not_called()
            window.assert_not_called()
        overlay.destroy()

    def test_typed_questions_get_fresh_images_even_when_the_screen_is_unchanged(self):
        settings = dict(app._default_settings(), backend="codex", vision_mode="periodic", vision_target="desktop")
        overlay = app.OverlayScreen(self.root, settings, lambda: None)
        with mock.patch.object(overlay.capture, "take", return_value="fresh-frame") as capture, \
                mock.patch.object(app, "image_to_base64_jpeg", return_value="image64"), \
                mock.patch.object(app, "ask_ai_vision", return_value="I can see the example channel.") as vision, \
                mock.patch.object(app, "ask_ai") as text:
            for index, question in enumerate(("What are you looking at?", "Can you see the YouTube channel?"), 1):
                overlay._manual_entry.event_generate("<FocusIn>")
                overlay._manual_entry.insert("1.0", question)
                overlay._send_manual()
                self.pump_until(lambda: len(overlay.hud.answers) == index)
                self.assertEqual(vision.call_args.args[2]["vision_question"], question)
                self.assertEqual(vision.call_args.args[2]["vision_target"], "desktop")
                self.assertEqual(vision.call_args.args[0], "image64")
            self.assertEqual(capture.call_count, 2)
            self.assertEqual(vision.call_count, 2)
            overlay.analyze_screen(overlay._active_token(), periodic=True)
            self.assertEqual(vision.call_count, 2, "Automatic checks skip unchanged frames")
            text.assert_not_called()
        overlay.destroy()

    def test_question_preempts_old_periodic_answer_and_is_not_dropped(self):
        settings = dict(app._default_settings(), backend="codex", vision_mode="periodic", vision_target="desktop")
        overlay = app.OverlayScreen(self.root, settings, lambda: None)
        entered = threading.Event()
        def reply(_image, _context, settings, active):
            if settings.get("vision_question"):
                return "The current question was answered with an image."
            entered.set()
            deadline = time.monotonic() + 2
            while active() and time.monotonic() < deadline:
                time.sleep(.01)
            return "Old passive screen description"
        with mock.patch.object(overlay.capture, "take", return_value="frame"), \
                mock.patch.object(app, "image_to_base64_jpeg", return_value="image64"), \
                mock.patch.object(app, "ask_ai_vision", side_effect=reply):
            worker = threading.Thread(target=overlay.analyze_screen, args=(overlay._active_token(), True))
            worker.start()
            self.pump_until(entered.is_set)
            overlay._manual_entry.event_generate("<FocusIn>")
            overlay._manual_entry.insert("1.0", "What is visible now?")
            overlay._send_manual()
            self.pump_until(lambda: len(overlay.hud.answers) == 1)
            worker.join(1)
            self.assertFalse(worker.is_alive())
            self.assertIn("current question", overlay.hud.text.get("1.0", "end"))
            self.assertNotIn("Old passive", overlay.hud.text.get("1.0", "end"))
        overlay.destroy()

    def test_turning_vision_off_drops_a_queued_screen_answer(self):
        settings = dict(app._default_settings(), backend="codex", vision_mode="manual", vision_target="desktop")
        overlay = app.OverlayScreen(self.root, settings, lambda: None)
        with mock.patch.object(overlay.capture, "take", return_value="frame"), \
                mock.patch.object(app, "image_to_base64_jpeg", return_value="image64"), \
                mock.patch.object(app, "ask_ai_vision", return_value="Stale screen answer"), \
                mock.patch.object(app, "save_settings"):
            worker = threading.Thread(target=overlay.analyze_screen, args=(overlay._active_token(),))
            worker.start()
            worker.join(1)
            self.assertFalse(worker.is_alive())
            overlay._set_desktop_watch(False)
            self.root._dispatcher._drain()
            self.assertFalse(overlay.hud.answers)
        overlay.destroy()

    def test_setup_constructs_and_all_backend_panels_toggle(self):
        with mock.patch.object(app.CODEX, "status") as status:
            status.return_value.label.return_value = "Test status"
            settings = app._default_settings()
            screen = app.SetupScreen(self.root, settings, lambda _: None)
            for backend in app.BACKEND_CHOICES:
                screen._vars["backend"].set(backend)
                screen._refresh()
                self.root.update_idletasks()
            screen.destroy()

    def test_overlay_constructs_and_clear_invalidates_queued_callbacks(self):
        overlay = app.OverlayScreen(self.root, app._default_settings(), lambda: None)
        self.root.update_idletasks()
        active = overlay._active_token()
        calls = []
        worker = threading.Thread(target=lambda: overlay._post(lambda: calls.append("stale")))
        worker.start()
        worker.join()
        overlay.clear()
        self.root._dispatcher._drain()
        self.assertFalse(active())
        self.assertEqual(calls, [])
        overlay.destroy()

    def test_hud_math_code_navigation_pin_and_copy(self):
        hud = AnswerHud(self.root, app._default_settings(), app.C, self.root._dispatcher)
        math = json.dumps({"type": "math", "summary": "x = 6", "latex": "x=6", "steps": ["2x=12"]})
        hud.add(math)
        hud.set_detail("detailed")
        self.assertEqual(hud.detail, "detailed")
        hud.pin()
        hud.add(json.dumps({"type": "code", "code": "print('hello')", "language": "python"}))
        self.assertEqual(hud.index, 0)
        hud.move(1)
        hud.set_detail("normal")
        self.assertIn("print('hello')", hud.text.get("1.0", "end"))
        hud.copy()
        self.assertIn("```python", self.root.clipboard_get())
        hud.resize(1)
        hud.toggle()
        hud.clear()
        self.assertFalse(hud.answers)
        hud.close()
        hud.destroy()

    def test_debug_panel_requires_opt_in_and_constructs(self):
        settings = dict(app._default_settings(), developer_mode=True)
        panel = DebugPanel(self.root, settings, self.root._dispatcher,
                           app.os.path.dirname(app.__file__), [])
        panel.inspect()
        self.assertIn("Zoom Co-Pilot", panel.output.get("1.0", "end"))
        panel.reject()
        self.assertIsNone(panel.proposal)
        panel.destroy()
