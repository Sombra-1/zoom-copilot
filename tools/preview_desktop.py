"""Open the real desktop UI with synthetic meeting content for review."""
import argparse
import json
from pathlib import Path
import sys
import tempfile
import time
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import zoom_copilot as app
from copilot_core.vision_capture import root_handle


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshots", type=Path, help="Save images of the app's own windows and exit")
    args = parser.parse_args()
    settings = dict(app._default_settings(), backend="demo", transcription="local", opacity=1.0)
    with tempfile.TemporaryDirectory() as folder, \
            mock.patch.object(app, "load_settings", side_effect=lambda: dict(settings)), \
            mock.patch.object(app, "save_settings"), \
            mock.patch("copilot_core.vision_capture.CaptureController.probe", return_value=False):
        gui = app.App(support_state_file=Path(folder) / "support.json", check_updates=False)
        root = gui.root
        root.title("Zoom Copilot · v2.1 Preview")
        gui._capture_hidden[0] = False
        app.set_affinity(root, False)

        def workspace():
            gui._launch(settings)
            app.fit_window(root, 940, 730, minimum=(680, 560))
            screen = gui.current
            screen.append_message("Demo transcript", "The team will review the onboarding guide on Friday.", "them")
            screen.append_message("Demo transcript", "Alex will send the draft and list unresolved questions.", "them")
            screen.hud.add(json.dumps({"type": "answer", "title": "Friday's review is the next checkpoint",
                                       "summary": "Alex will circulate the onboarding guide before the review.",
                                       "bullets": ["Review the draft with the team on Friday.",
                                                   "Track unresolved questions in the meeting notes."]}))

        try:
            if args.snapshots:
                from PIL import ImageGrab

                args.snapshots.mkdir(parents=True, exist_ok=True)

                def save(name):
                    root.update()
                    time.sleep(0.25)
                    root.update()
                    ImageGrab.grab(window=root_handle(root)).save(args.snapshots / name)

                save("Zoom-Copilot-v2.1-Setup.png")
                workspace()
                save("Zoom-Copilot-v2.1-Workspace.png")
            else:
                workspace()
                root.mainloop()
        finally:
            gui._quit()


if __name__ == "__main__":
    main()
