"""Brand assets, native launcher format and window-icon integration."""
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest import mock

import zoom_copilot as app
from copilot_core.branding import ASSETS, apply_window_icon, logo_label
from copilot_core.ui_theme import destroy_root


class BrandingTests(unittest.TestCase):
    def test_logo_without_pillow_keeps_the_header_within_its_size_budget(self):
        root = app.ctk.CTk()
        try:
            with mock.patch.dict(sys.modules, {"PIL": None, "PIL.Image": None}):
                label = logo_label(root, size=28)
            label.pack()
            root.update()
            self.assertTrue(label.cget("image"))
            self.assertLessEqual(label.winfo_height(), round(28 * root._get_window_scaling()) + 2)
        finally:
            destroy_root(root)
    def test_windows_icon_contains_small_and_high_dpi_sizes(self):
        data = (ASSETS / "app.ico").read_bytes()
        reserved, kind, count = struct.unpack_from("<HHH", data)
        self.assertEqual((reserved, kind), (0, 1))
        sizes = {data[6 + n * 16] or 256 for n in range(count)}
        self.assertTrue({16, 20, 24, 32, 48, 64, 128, 256}.issubset(sizes))

    def test_native_launcher_has_gui_subsystem_and_embedded_resources(self):
        data = (ASSETS.parent / "Zoom Copilot.exe").read_bytes()
        self.assertEqual(data[:2], b"MZ")
        header = struct.unpack_from("<I", data, 0x3c)[0]
        self.assertEqual(data[header:header+4], b"PE\0\0")
        optional = header + 24
        self.assertEqual(struct.unpack_from("<H", data, optional+68)[0], 2)
        directories = optional + (96 if struct.unpack_from("<H", data, optional)[0] == 0x10b else 112)
        self.assertGreater(struct.unpack_from("<I", data, directories+16)[0], 0)

    @unittest.skipUnless(sys.platform == "win32", "Windows icon bitmap")
    def test_icon_is_set_as_default_and_current_window_icon(self):
        root = mock.Mock()
        apply_window_icon(root)
        self.assertEqual(root.iconbitmap.call_count, 2)
        root.iconbitmap.assert_any_call(default=str(ASSETS / "app.ico"))

    def test_application_keeps_its_icon_after_customtkinter_startup(self):
        with tempfile.TemporaryDirectory() as folder, \
                mock.patch.object(app, "load_settings", side_effect=lambda: dict(app._default_settings(), backend="demo")):
            gui = app.App(support_state_file=Path(folder) / "usage.json", check_updates=False)
            try:
                gui.root.update()
                if sys.platform == "win32":
                    self.assertTrue(gui.root._iconbitmap_method_called)
                self.assertEqual(gui.root.title(), "Zoom Copilot")
            finally:
                gui._quit()
