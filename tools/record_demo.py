"""Record only this app's window with synthetic data; never load user settings.

Run with the project's Python: python tools/record_demo.py
Requires optional Pillow and an interactive Windows desktop. Frames go to work/.
No microphone, screen-watch service, AI provider, or support website is used.
"""
import ctypes
import json
from pathlib import Path
import sys
import tempfile
from unittest import mock

from PIL import ImageGrab, ImageOps

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import zoom_copilot as app  # noqa: E402
from copilot_core import overlay_view, setup_view  # noqa: E402


def main():
    if sys.platform != "win32":
        raise SystemExit("The demo recorder currently requires Windows.")
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except OSError:
        pass
    media = ROOT / "docs" / "media"
    frames = ROOT / "work" / "demo-frames"
    media.mkdir(parents=True, exist_ok=True)
    frames.mkdir(parents=True, exist_ok=True)
    settings = dict(app._default_settings(), backend="demo", transcription="local", opacity=1.0)
    with tempfile.TemporaryDirectory() as folder, \
            mock.patch.object(app, "load_settings", side_effect=lambda: dict(settings)), \
            mock.patch.object(app, "save_settings"), \
            mock.patch("copilot_core.vision_capture.CaptureController.probe", return_value=False):
        gui = app.App(support_state_file=Path(folder) / "support.json", check_updates=False)
        root = gui.root
        gui._capture_hidden[0] = False
        app.set_affinity(root, False)
        root.geometry("1000x730+50+30")
        root.attributes("-alpha", 1.0)
        root.lift()

        def snapshot(name):
            root.update_idletasks()
            x, y = root.winfo_rootx(), root.winfo_rooty()
            image = ImageGrab.grab(bbox=(x, y, x + root.winfo_width(), y + root.winfo_height()))
            if name:
                image.save(media / name)
            return image

        def workspace():
            gui._launch(settings)
            root.geometry("1000x730+50+30")
            root.attributes("-alpha", 1.0)
            gui.current.capture.probe = lambda: False
            app.set_affinity(root, False)
            gui.current.append_message("DEMO TRANSCRIPT", "Ship the onboarding guide on Friday. Alex owns the draft.", "them")
            gui.current.hud.add(json.dumps({"type": "answer", "title": "A little clarity. Right when you need it.",
                                           "summary": "Friday's launch: the onboarding guide comes first.",
                                           "bullets": ["Alex owns the first draft.", "Confirm the review time before the meeting ends."]}))

        def controls():
            overlay_view.toggle_vision(gui.current)

        def support():
            if gui.current._vision_expanded:
                overlay_view.toggle_vision(gui.current)
            gui._community.usage.seconds = 10800
            gui._community.sync()

        def small():
            root.geometry("680x560+50+30")
            gui._updates.complete("2.1.0", False)

        def record(index=0):
            frame = ImageOps.pad(snapshot(None), (1280, 960), color="#101216")
            frame.save(frames / (f"{index:04d}.png"))
            if index < 169:
                root.after(100, lambda: record(index + 1))
            else:
                small()
                root.after(400, lambda: finish())

        def finish():
            # Example future release is used only for local layout QA, not published media.
            snapshot(None).save(ROOT / "work" / "small-notices.png")
            gui._quit()

        root.after(1000, lambda: snapshot("settings.png"))
        root.after(1600, record)
        root.after(3500, lambda: setup_view.show_page(gui.current, "preferences"))
        root.after(5800, workspace)
        root.after(7600, lambda: snapshot("workspace.png"))
        root.after(9500, controls)
        root.after(12500, support)
        root.after(14200, lambda: snapshot("support.png"))
        root.mainloop()
    print("Synthetic app screenshots and 170 frames saved.")


if __name__ == "__main__":
    main()
