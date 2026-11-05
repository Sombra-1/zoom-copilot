"""Overlay service controls, capture orchestration and request lifecycle."""
import hashlib
import threading
import time
import tkinter as tk

from .codex_backend import SERVICE
from .codex_client import Cancelled
from .backends import backend_is_local
from .vision_capture import list_windows


class OverlayServices:
    def _later(self, delay, callback):
        """Track delayed widget work so switching views cancels its Tcl timer."""
        active = self._active_token()
        if not hasattr(self, "_ui_timers"):
            self._ui_timers = set()
        def run():
            self._ui_timers.discard(timer)
            if active():
                callback()
        timer = self.after(delay, run)
        self._ui_timers.add(timer)
        return timer

    def _post(self, callback):
        active = self._active_token()
        return self.dispatcher.post(lambda: callback() if active() else None)

    def _active_token(self):
        epoch = self._request_epoch
        return lambda: self._alive.is_set() and self._request_epoch == epoch

    def _prioritize_screen_question(self):
        with self.runtime["_history_lock"]:
            self._screen_question_serial = getattr(self, "_screen_question_serial", 0) + 1

    def _invalidate_requests(self):
        with self.runtime["_history_lock"]:
            self._request_epoch += 1
        SERVICE.close()
        if hasattr(self, "_notes_btn"):
            self._notes_btn.config(state="normal", text="Make notes")

    def _close_region_selector(self):
        pending = getattr(self, "_selector_after_id", None)
        if pending:
            self.after_cancel(pending)
            self._selector_after_id = None
        selector = getattr(self, "_region_selector", None)
        if selector is not None and selector.winfo_exists():
            selector.destroy()
        self._region_selector = None
        if getattr(self, "_region_hidden", False):
            self._region_hidden = False
            self.master.deiconify()

    def destroy(self):
        self._alive.clear()
        self.runtime["_end_screen_session"]()
        self._close_region_selector()
        for timer in getattr(self, "_ui_timers", ()):
            self.after_cancel(timer)
        self._stop_pulse()
        pending_probe = getattr(self, "_probe_after_id", None)
        if pending_probe:
            self.after_cancel(pending_probe)
        binding = getattr(self, "_listen_binding", None)
        if binding:
            self.master.unbind("<Control-l>", binding)
        binding = getattr(self, "_watch_binding", None)
        if binding:
            self.master.unbind("<Control-Shift-S>", binding)
        self._invalidate_requests()
        self.capture.close()
        self.hud.close()
        for panel in getattr(self, "_debug_panels", []):
            if panel.winfo_exists():
                panel.destroy()
        super().destroy()

    def _build_vision_controls(self):
        c = self.runtime["C"]
        row = tk.Frame(self, bg=c["bg"])
        row.pack(fill="x", padx=14, pady=3)
        self._vision_mode = tk.StringVar(value=self.s.get("vision_mode", "off"))
        self._vision_target = tk.StringVar(value=self.s.get("vision_target", "region"))
        self._present = tk.BooleanVar(value=self.s.get("presentation_mode", False))
        tk.Label(row, text="Vision", bg=c["bg"], fg=c["fg2"]).pack(side="left")
        for variable, choices in ((self._vision_mode, ("off", "manual", "periodic")),
                                  (self._vision_target, ("region", "window", "screen"))):
            menu = tk.OptionMenu(row, variable, *choices, command=lambda _: self._vision_changed())
            menu.config(bg=c["panel2"], fg=c["fg"], relief="flat", highlightthickness=0, font=("Segoe UI", 9))
            menu["menu"].config(bg=c["panel2"], fg=c["fg"])
            menu.pack(side="left", padx=2)
        self._window_button = tk.Button(row, text="Select window", command=self._pick_window,
                                        bg=c["panel2"], fg=c["fg2"], relief="flat")
        self._window_button.pack(side="left", padx=2)
        tk.Button(row, text="Capture now", command=self._manual_capture, bg=c["panel2"],
                  fg=c["accent"], relief="flat").pack(side="left", padx=2)
        tk.Checkbutton(row, text="Present", variable=self._present, command=self._vision_changed,
                       bg=c["bg"], fg=c["fg2"], selectcolor=c["panel2"]).pack(side="left")
        self._vision_privacy = tk.Label(self, text="", bg=c["bg"], fg=c["warn"],
                                        font=("Segoe UI", 9), anchor="w")
        self._vision_privacy.pack(fill="x", padx=16)
        self._capture_notice = "capture test pending"
        self._refresh_vision_label()

    def _refresh_vision_label(self):
        mode = self.s.get("vision_mode", "off")
        provider = self.s["backend"].title()
        location = "Local" if backend_is_local(self.s) else ("Remote" if self.s["backend"] == "ollama" else "Cloud")
        scope = {"desktop": "All displays", "screen": "Primary screen", "window": "Window", "region": "Region"}.get(self.s.get("vision_target"), "Region")
        state = "watching" if self.runtime["_screen_watch_event"].is_set() else "on questions"
        stamp = getattr(self, "_last_screen_at", "")
        label = "Vision off · questions use text only" if mode == "off" else f"{scope} · {provider} {location} · {state}" + (f" · {stamp}" if stamp else "")
        self._vision_privacy.config(text=label)

    def _set_desktop_watch(self, enabled):
        self._close_region_selector()
        if enabled:
            if not self.runtime["screen_capture_available"]() or not self.runtime["backend_supports_vision"](self.s):
                self._desktop_watch.set(False)
                self.append_message("ERROR", "Screen watching requires screen-capture support and Codex, Claude, or a vision-capable Ollama model.", "error")
                return
            self._vision_target.set("desktop")
            self._vision_mode.set("periodic")
            self._vision_changed()
            self._start_screen_watch()
        else:
            self._vision_mode.set("off")
            self._vision_changed()
        self.set_status(*self.runtime["live_status_args"]())

    def _toggle_desktop_watch(self):
        running = self.runtime["_screen_watch_event"].is_set() and self.s.get("vision_target") in ("screen", "desktop")
        self._set_desktop_watch(not running)

    def _probe_capture(self):
        if self._alive.is_set():
            self.capture.probe()
            self._capture_notice = "capture exclusion verified" if self.capture.verified else "private frame hiding enabled"
            self._refresh_vision_label()

    def _vision_changed(self):
        self._vision_epoch = getattr(self, "_vision_epoch", 0) + 1
        self.runtime["_end_screen_session"]()
        self.s["vision_mode"] = self._vision_mode.get()
        self.s["vision_target"] = self._vision_target.get()
        self.s["presentation_mode"] = self._present.get()
        self._previous_screen = None
        self._last_screen_at = ""
        self._screen_btn.config(text="Watch", bg="transparent", fg=self.runtime["C"]["fg2"])
        self.runtime["save_settings"](self.s)
        self._refresh_vision_label()
        from .overlay_view import refresh_vision_controls
        refresh_vision_controls(self)
        self.set_status(*self.runtime["live_status_args"]())

    def _pick_window(self):
        self.runtime["_end_screen_session"]()
        self._vision_epoch = getattr(self, "_vision_epoch", 0) + 1
        self._screen_btn.config(text="Watch", bg="transparent", fg=self.runtime["C"]["fg2"])
        self._refresh_vision_label()
        from .overlay_view import refresh_vision_controls
        refresh_vision_controls(self)
        rows = list_windows()
        if not rows:
            self.append_message("ERROR", "Window capture is available on Windows. Use a selected region on other platforms.", "error")
            return
        c = self.runtime["C"]
        dialog = tk.Toplevel(self.master)
        dialog.title("Select an application window")
        dialog.geometry("480x340")
        dialog.configure(bg=c["bg"])
        choices = tk.Listbox(dialog, bg=c["panel"], fg=c["fg"], selectmode="single")
        choices.pack(fill="both", expand=True, padx=10, pady=10)
        for _, title in rows:
            choices.insert("end", title)
        def select():
            if not self._alive.is_set():
                dialog.destroy()
                return
            indices = choices.curselection()
            if indices:
                self._selected_window = rows[indices[0]][0]
                title = rows[indices[0]][1]
                self._window_button.config(text=title[:14] + ("…" if len(title) > 14 else ""))
                self._vision_target.set("window")
                self._vision_changed()
            dialog.destroy()
        tk.Button(dialog, text="Use selected window", command=select).pack(pady=7)

    def _manual_capture(self):
        overlay_active = self._active_token()
        epoch = getattr(self, "_vision_epoch", 0)
        active = lambda: overlay_active() and getattr(self, "_vision_epoch", 0) == epoch
        # The capture button explicitly submits the current question with the image.
        question = "" if self._input_has_placeholder else self._manual_entry.get("1.0", "end").strip()
        settings = dict(self.s, vision_question=question)
        self._prioritize_screen_question()
        threading.Thread(target=self.analyze_screen, args=(active, False, settings), daemon=True).start()

    def analyze_screen(self, active, periodic=False, settings=None):
        runtime = self.runtime
        settings = dict(settings or self.s)
        base_active, epoch = active, getattr(self, "_vision_epoch", 0)
        serial = getattr(self, "_screen_question_serial", 0)
        active = lambda: (base_active() and epoch == getattr(self, "_vision_epoch", 0) and
                          (not periodic or serial == getattr(self, "_screen_question_serial", 0)))
        acquired = False
        failed = False
        def post(callback):
            self._post(lambda: callback() if active() else None)
        try:
            if settings.get("vision_mode", "off") == "off" or not active():
                return
            if not runtime["backend_supports_vision"](settings):
                raise RuntimeError("Select Codex, Claude or a vision-capable Ollama model")
            if periodic:
                acquired = self._screen_inflight.acquire(blocking=False)
            else:
                deadline = time.monotonic() + settings.get("codex_timeout", 120)
                while active() and not acquired:
                    acquired = self._screen_inflight.acquire(timeout=.05)
                    if not acquired and time.monotonic() > deadline:
                        raise RuntimeError("Screen analysis is busy. Try your question again.")
            if not acquired or not active():
                return
            post(lambda: self.set_status("Reading current screen…"))
            image = self.capture.take(settings, runtime["_screen_region"]["coords"], self._selected_window, active)
            if not active() or self.s.get("vision_mode") == "off":
                return
            encoded = runtime["image_to_base64_jpeg"](image, max_width=1920)
            digest = hashlib.sha256(encoded.encode("ascii")).digest()
            if periodic and digest == getattr(self, "_previous_screen", None):
                return
            context = "\n".join(runtime["get_transcript_lines"](limit=8))
            if settings.get("vision_question"):
                context += "\n\nUSER QUESTION: " + settings["vision_question"]
            stamp = time.strftime("%H:%M:%S")
            def captured():
                self._last_screen_at = stamp
                self._refresh_vision_label()
                self.set_status("AI thinking...")
            post(captured)
            runtime["_stats_inc"]("ai_calls")
            reply = runtime["ask_ai_vision"](encoded, context, settings, active=active)
            if not active():
                return
            self._previous_screen = digest
            with runtime["_history_lock"]:
                if not active():
                    return
                runtime["conversation_history"].append({"role": "assistant", "content": f"[SCREEN] {reply}"})
            post(lambda: self.append_message("Copilot" if settings.get("vision_question") else "SCREEN", reply, "ai"))
        except Cancelled:
            pass
        except Exception as exc:
            failed = True
            if active():
                runtime["_stats_inc"]("errors")
                message = f"Screen capture/vision failed: {exc}"
                post(lambda: self.append_message("ERROR", message, "error"))
        finally:
            if acquired:
                self._screen_inflight.release()
            if active() and (acquired or failed):
                post(lambda: self.set_status(*runtime["live_status_args"]()))
                post(self.update_stats)

    def _open_debug(self):
        from .debug_panel import DebugPanel
        panel = DebugPanel(self.master, self.s, self.dispatcher,
                   self.runtime["os"].path.dirname(self.runtime["__file__"]),
                   [item["text"] for item in self._chat_items if item["kind"] == "error"])
        if not hasattr(self, "_debug_panels"):
            self._debug_panels = []
        self._debug_panels.append(panel)
