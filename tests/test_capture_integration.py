"""Opt-in local pixel tests. Captures only synthetic test windows, never uploads."""
import os
import sys
import threading
import time
import tkinter as tk
import unittest
import gc

import zoom_copilot as app
from copilot_core.ui_dispatch import UiDispatcher
from copilot_core.vision_capture import CaptureController, capture_window, root_handle, set_affinity


@unittest.skipUnless(sys.platform == "win32" and os.environ.get("COPILOT_CAPTURE_TESTS") == "1",
                     "Set COPILOT_CAPTURE_TESTS=1 on an interactive Windows desktop")
class CaptureIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.geometry("420x320+100+100")
        self.root.configure(bg="#16b35b")
        self.root.attributes("-topmost", True)
        tk.Label(self.root, text="SYNTHETIC CAPTURE TEST", bg="white", fg="black").pack(anchor="nw")
        self.front = tk.Toplevel(self.root)
        self.front.overrideredirect(True)
        self.front.geometry("120x100+180+180")
        self.front.configure(bg="#fa16cf")
        self.front.attributes("-topmost", True)
        self.root.update()
        self.dispatcher = UiDispatcher(self.root)
        self.capture = CaptureController(self.front, self.dispatcher, app.capture_screen)

    def tearDown(self):
        self.capture.close()
        self.dispatcher.close()
        self.root.update()
        self.root.destroy()
        self.capture = self.dispatcher = self.front = self.root = None
        gc.collect()

    def take(self):
        result = {}
        def worker():
            try:
                result["image"] = self.capture.take({"vision_mode": "manual", "vision_target": "region"},
                                                     (100, 140, 500, 400))
            except Exception as exc:
                result["error"] = exc
        thread = threading.Thread(target=worker)
        thread.start()
        deadline = time.monotonic() + 8
        while thread.is_alive() and time.monotonic() < deadline:
            self.root.update()
            time.sleep(0.01)
        thread.join(timeout=1)
        if "error" in result:
            raise result["error"]
        return result["image"]

    def test_actual_capture_exclusion_and_underlying_content(self):
        self.assertTrue(self.capture.probe(), "This capture path did not pass Windows exclusion probe")
        self.assertTrue(set_affinity(self.front, True))
        image = self.take()
        self.assertEqual(image.convert("RGB").getpixel((120, 80)), (22, 179, 91))
        self.assertEqual(self.front.state(), "normal")

    def test_unverified_capture_hides_frame_and_restores(self):
        self.capture.verified = False
        image = self.take()
        self.assertEqual(image.convert("RGB").getpixel((120, 80)), (22, 179, 91))
        self.assertEqual(self.front.state(), "normal")

    def test_probe_with_application_auto_exclusion_map_hook(self):
        def mapped(event):
            if isinstance(event.widget, (tk.Tk, tk.Toplevel)):
                set_affinity(event.widget, True)
        self.root.bind_all("<Map>", mapped, add="+")
        self.assertTrue(self.capture.probe())

    def test_direct_window_capture_excludes_occluding_overlay(self):
        result = {}
        handle = root_handle(self.root)
        def worker():
            try:
                result["image"] = capture_window(handle)
            except Exception as exc:
                result["error"] = exc
        thread = threading.Thread(target=worker)
        thread.start()
        while thread.is_alive():
            self.root.update()
            time.sleep(0.01)
        if "error" in result:
            raise result["error"]
        image = result["image"]
        self.assertEqual(image.convert("RGB").getpixel((120, 120)), (22, 179, 91))
