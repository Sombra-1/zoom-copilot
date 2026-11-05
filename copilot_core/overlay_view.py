"""Modern meeting workspace. The existing overlay controller owns behavior."""
import tkinter as tk
import customtkinter as ctk

from .ui_theme import COLORS as C, Button, Label, card, row, select, text_surface
from .answer_renderer import AnswerHud
from .support_ui import workspace_links
from .branding import logo_label
from .update_ui import notice as update_notice


def build(screen):
    runtime = screen.runtime
    screen.configure(bg=C["bg"])
    screen.grid_columnconfigure(0, weight=1)
    screen.grid_rowconfigure(2, weight=1)
    header = row(screen)
    header.grid(row=0, column=0, sticky="ew", padx=22, pady=(18, 10))
    logo_label(header, size=28).pack(side="left", padx=(0, 10))
    Label(header, "Zoom Copilot", size=20, bold=True).pack(side="left")
    provider = screen.s["backend"].title()
    Label(header, provider, size=11, text_color=C["accent"], fg_color="#252b42", corner_radius=6,
          padx=9, width=72, height=26).pack(side="left", padx=12)
    Button(header, "Settings", command=screen.on_settings, width=78, quiet=True).pack(side="right")
    if screen.on_toggle_capture and runtime["sys"].platform == "win32":
        screen._capture_btn = Button(header, "Checking privacy", command=lambda: screen.on_toggle_capture(screen._capture_btn),
                                     width=136, height=30, quiet=True, text_color=C["fg2"])
        screen._capture_btn.pack(side="right", padx=4)
    status = row(screen)
    status.grid(row=1, column=0, sticky="ew", padx=24, pady=(0, 12))
    screen.status_lbl = Label(status, "●  Ready", size=12, muted=True, wraplength=550, justify="left")
    screen.status_lbl.pack(side="left", fill="x", expand=True)
    privacy, _, _ = runtime["privacy_mode_label"](screen.s)
    Label(status, {"LOCAL-FIRST": "Local processing", "LOCAL STT": "Local transcript",
                   "LOCAL AI": "Local AI · cloud transcript", "CLOUD": "Cloud connection"}.get(privacy, privacy),
          size=11, muted=True).pack(side="right")
    screen._error_btn = Button(status, "Error · details", command=lambda: show_errors(screen),
                               quiet=True, width=108, height=26, text_color=C["error"])
    screen._body = row(screen)
    screen._body.grid(row=2, column=0, sticky="nsew", padx=20)
    screen._body.grid_columnconfigure(0, weight=1)
    screen._body.grid_rowconfigure(0, weight=3, minsize=160)
    screen._body.grid_rowconfigure(1, weight=2, minsize=96)
    screen.hud = AnswerHud(screen._body, screen.s, C, screen.dispatcher)
    screen.hud.grid(row=0, column=0, sticky="nsew", pady=(0, 12))
    screen._transcript_card = card(screen._body)
    screen._transcript_card.grid(row=1, column=0, sticky="nsew")
    log_header = row(screen._transcript_card)
    log_header.pack(fill="x", padx=12, pady=(10, 4))
    build_filters(screen, log_header)
    screen._notes_btn = Button(log_header, "Make notes", command=screen._generate_meeting_notes, width=100, height=29, quiet=True)
    screen._notes_btn.pack(side="right", padx=3)
    menu_button = Button(log_header, "···", width=32, height=29, quiet=True)
    menu_button.pack(side="right")
    wrapper, screen.chat = text_surface(screen._transcript_card, height=4, state="disabled", cursor="arrow")
    wrapper.pack(fill="both", expand=True, padx=12, pady=(2, 9))
    configure_chat(screen)
    screen._ctx_menu = tk.Menu(screen.chat, tearoff=False, bg=C["panel2"], fg=C["fg"],
                                activebackground=C["btn_hover"], activeforeground=C["fg"], bd=0,
                                font=("Segoe UI", -13))
    screen._ctx_menu.add_command(label="Copy selection", command=lambda: copy_selection(screen))
    screen._ctx_menu.add_command(label="Copy last answer", command=screen._copy_last_ai)
    screen._ctx_menu.add_separator()
    screen._ctx_menu.add_command(label="Export meeting notes…", command=screen.export_meeting_markdown)
    screen._ctx_menu.add_command(label="Save session text…", command=screen.save_transcript)
    if screen.s.get("developer_mode"):
        screen._ctx_menu.add_command(label="Developer tools…", command=screen._open_debug)
    screen._ctx_menu.add_separator()
    screen._ctx_menu.add_command(label="Clear session", command=screen.clear)
    menu_button.config(command=lambda: screen._ctx_menu.tk_popup(menu_button.winfo_rootx(), menu_button.winfo_rooty() + menu_button.winfo_height()))
    screen.chat.bind("<Button-3>", lambda e: screen._ctx_menu.tk_popup(e.x_root, e.y_root))
    screen._autoscroll = [True]
    screen._render_chat_log()
    screen._scroll_btn = Button(log_header, "Follow", command=screen._toggle_autoscroll, width=62, height=29, quiet=True)
    screen._scroll_btn.pack(side="right", padx=3)
    # Privacy stays visible even while the optional controls are collapsed.
    vision_header = row(screen)
    vision_header.grid(row=3, column=0, sticky="ew", padx=22, pady=(10, 4))
    screen._desktop_watch = tk.BooleanVar(value=False)
    screen._desktop_switch = ctk.CTkSwitch(vision_header, text="Watch screen", variable=screen._desktop_watch,
                                           command=lambda: screen._set_desktop_watch(screen._desktop_watch.get()),
                                           fg_color=C["border2"], progress_color=C["accent2"],
                                           font=("Segoe UI", 12), width=130)
    screen._desktop_switch.pack(side="left")
    screen._vision_toggle = Button(vision_header, "Controls  ▾", command=lambda: toggle_vision(screen), width=86, height=28, quiet=True)
    screen._vision_toggle.pack(side="right")
    screen._vision_privacy = Label(vision_header, "Vision off · no screenshots sent", size=11, muted=True)
    screen._vision_privacy.pack(side="left", padx=8, fill="x", expand=True)
    screen._focus = False
    screen._auto_compact = False
    screen._compact_activity = False
    screen._layout_mode = None
    screen._focus_btn = Button(vision_header, "Focus view", command=lambda: toggle_focus(screen), width=92, height=28, quiet=True)
    screen._focus_btn.pack(side="right")
    screen._vision_frame = card(screen)
    screen._vision_frame.grid(row=4, column=0, sticky="ew", padx=20, pady=(0, 8))
    build_vision(screen, screen._vision_frame)
    screen._vision_expanded = screen.s.get("vision_mode", "off") != "off"
    if not screen._vision_expanded:
        screen._vision_frame.grid_remove()
    compose = card(screen)
    compose.grid(row=5, column=0, sticky="ew", padx=20, pady=(4, 10))
    build_composer(screen, compose)
    refresh_vision_controls(screen)
    footer = row(screen)
    footer.grid(row=6, column=0, sticky="ew", padx=22, pady=(0, 5))
    screen.toggle_btn = Button(footer, "Start listening", primary=True, width=148, height=36, command=screen.toggle_listening)
    screen.toggle_btn.pack(side="left")
    screen._stats_lbl = Label(footer, "Ready for your next meeting", size=11, muted=True)
    screen._stats_lbl.pack(side="left", padx=14, fill="x", expand=True)
    Label(footer, "Opacity", size=11, muted=True).pack(side="right", padx=(8, 0))
    screen.opacity_var = tk.DoubleVar(value=screen.s.get("opacity", .94))
    ctk.CTkSlider(footer, from_=.3, to=1.0, variable=screen.opacity_var, width=78, height=16,
                  fg_color=C["border"], progress_color=C["border2"], button_color=C["fg2"],
                  button_hover_color=C["accent"], command=lambda value: screen.master.attributes("-alpha", float(value))).pack(side="right")
    screen.master.attributes("-alpha", screen.s.get("opacity", .94))
    screen._listen_binding = screen.master.bind("<Control-l>", lambda _: screen.toggle_listening(), add="+")
    screen._watch_binding = screen.master.bind("<Control-Shift-S>", lambda _: screen._toggle_desktop_watch(), add="+")
    screen._body.bind("<Configure>", lambda _: adapt_layout(screen), add="+")
    runtime["_tip"](screen.toggle_btn, "Start or stop transcription · Ctrl+L")
    runtime["_tip"](screen._desktop_switch, "Watch all displays · Ctrl+Shift+S while Copilot is focused")
    workspace_links(screen)
    update_notice(screen)
    screen.append_message("SYSTEM", "Your meeting context appears here. Start listening, or ask a question below.", "ai")


def configure_chat(screen):
    chat = screen.chat
    scale = screen._body._get_widget_scaling()
    caption = ("Segoe UI", -round(11 * scale))
    chat.tag_config("them", foreground=C["them"], spacing3=2, lmargin1=4, lmargin2=4)
    chat.tag_config("them_lbl", foreground=C["fg2"], font=caption, spacing1=3)
    chat.tag_config("ai", foreground=C["ai"], spacing3=2, lmargin1=4, lmargin2=4)
    chat.tag_config("ai_lbl", foreground=C["accent"], font=caption, spacing1=3)
    chat.tag_config("error", foreground=C["error"])
    chat.tag_config("sys", foreground=C["fg2"], font=("Segoe UI", -round(12 * scale)))
    chat.tag_config("divider", foreground=C["border"])
    chat.tag_config("ts", foreground=C["fg2"], font=caption)


def build_filters(screen, parent):
    for name, label in (("All", "Activity"), ("Transcript", "Transcript"), ("AI", "Answers"), ("Notes", "Notes"), ("Errors", "Errors")):
        button = Button(parent, label, width=70 if name != "Transcript" else 86, height=29, quiet=True,
                        font=("Segoe UI", 11), command=lambda value=name: screen._set_chat_filter(value))
        button.pack(side="left", padx=(0, 3))
        screen._filter_buttons[name] = button
    screen._refresh_filter_tabs()


def refresh_filters(screen):
    titles = {"All": "Activity", "AI": "Answers"}
    for name, button in screen._filter_buttons.items():
        count = sum(1 for item in screen._chat_items if screen._chat_item_visible_for(item, name))
        title = titles.get(name, name)
        button.config(text=f"{title} {count}" if count else title,
                      bg=C["panel2"] if name == screen._chat_filter else "transparent",
                      fg=C["fg"] if name == screen._chat_filter else C["fg2"])


def build_vision(screen, parent):
    controls = row(parent)
    controls.pack(fill="x", padx=12, pady=10)
    screen._vision_mode = tk.StringVar(value=screen.s.get("vision_mode", "off"))
    screen._vision_target = tk.StringVar(value=screen.s.get("vision_target", "region"))
    screen._present = tk.BooleanVar(value=screen.s.get("presentation_mode", False))
    select(controls, screen._vision_mode, ("off", "manual", "periodic"), lambda _: screen._vision_changed(), width=94).pack(side="left", padx=(0, 7))
    names = {"region": "Region", "window": "Window", "screen": "Primary screen", "desktop": "All displays"}
    scope_label = tk.StringVar(value=names[screen._vision_target.get()])
    def scope_changed(value):
        screen._vision_target.set(next(key for key, name in names.items() if name == value))
        screen._vision_changed()
    screen._vision_target.trace_add("write", lambda *_: scope_label.set(names[screen._vision_target.get()]))
    select(controls, scope_label, names.values(), scope_changed, width=112).pack(side="left", padx=(0, 7))
    screen._region_btn = Button(controls, "Select region", command=screen._pick_region, width=106, height=32)
    screen._region_btn.pack(side="left", padx=(0, 7))
    screen._window_button = Button(controls, "Select window", command=screen._pick_window, width=112, height=32)
    screen._window_button.pack(side="left", padx=(0, 7))
    screen._capture_now_btn = Button(controls, "Capture", command=screen._manual_capture, primary=True, width=82, height=32)
    screen._capture_now_btn.pack(side="right")
    second = row(parent)
    second.pack(fill="x", padx=14, pady=(0, 10))
    screen._region_lbl = Label(second, "No region selected", size=11, muted=True)
    screen._region_lbl.pack(side="left", fill="x", expand=True)
    ctk.CTkSwitch(second, text="Talking points", variable=screen._present, command=screen._vision_changed,
                  fg_color=C["border2"], progress_color=C["accent2"], font=("Segoe UI", 11), width=128).pack(side="left", padx=12)
    screen._screen_btn = Button(second, "Watch", command=screen._toggle_screen_watch, width=80, height=28, quiet=True)
    screen._screen_btn.pack(side="right")
    screen._capture_notice = "capture test pending"
    screen._refresh_vision_label()
    refresh_vision_controls(screen)


def refresh_vision_controls(screen):
    mode = screen.s.get("vision_mode", "off")
    screen._capture_now_btn.config(state="disabled" if mode == "off" else "normal",
                                  bg=C["panel2"] if mode == "off" else C["accent2"])
    screen._screen_btn.config(state="normal" if mode == "periodic" else "disabled")
    running = screen.runtime["_screen_watch_event"].is_set()
    screen._screen_btn.config(text="Stop watch" if running else "Watch",
                              bg=C["panel2"] if running else "transparent",
                              fg=C["accent"] if running else C["fg2"])
    screen._desktop_watch.set(running and screen.s.get("vision_target") in ("screen", "desktop"))
    target = screen.s.get("vision_target")
    if target in ("desktop", "screen"):
        screen._region_lbl.config(text="Entire visible desktop · all displays" if target == "desktop" else "Primary display")
    elif target == "window":
        screen._region_lbl.config(text="Selected application window" if screen._selected_window else "Select an application window")
    else:
        coords = screen.runtime["_screen_region"]["coords"]
        screen._region_lbl.config(text=f"{coords[2]-coords[0]}×{coords[3]-coords[1]} selected region" if coords else "No region selected")
    if hasattr(screen, "_composer_hint"):
        screen._composer_hint.config(text="Enter to ask · current screen included" if mode != "off" else
                                     "Enter to ask · Shift+Enter for a new line")


def toggle_vision(screen):
    screen._vision_expanded = not screen._vision_expanded
    screen._vision_frame.grid() if screen._vision_expanded else screen._vision_frame.grid_remove()
    screen._vision_toggle.config(text="Controls  ▴" if screen._vision_expanded else "Controls  ▾")


def toggle_focus(screen):
    if screen._auto_compact:
        screen._compact_activity = not screen._compact_activity
    else:
        screen._focus = not screen._focus
    adapt_layout(screen)


def show_errors(screen):
    screen._compact_activity = True
    screen._focus = False
    adapt_layout(screen)
    screen._set_chat_filter("Errors")
    screen._error_btn.pack_forget()


def adapt_layout(screen):
    # A stable shared budget prevents a resize loop when compacting the
    # composer gives space back to the answer panel near the breakpoint.
    available = screen._body.winfo_height() + screen._composer.winfo_height()
    screen._auto_compact = available < 460 * screen._body._get_widget_scaling()
    mode = "activity" if screen._auto_compact and screen._compact_activity else (
        "answer" if screen._auto_compact or screen._focus else "both")
    if mode == screen._layout_mode:
        return
    screen._layout_mode = mode
    compact = mode != "both"
    screen._composer_content.grid_configure(columnspan=1 if compact else 2)
    screen._composer_send.grid_configure(row=0 if compact else 1, column=1,
                                         pady=(10, 10) if compact else (0, 10))
    if compact:
        screen._composer_hint.grid_remove()
    else:
        screen._composer_hint.grid()
    if mode == "answer":
        screen.hud.grid()
        screen._transcript_card.grid_remove()
        screen._body.grid_rowconfigure(0, weight=1, minsize=0)
        screen._body.grid_rowconfigure(1, weight=0, minsize=0)
    elif mode == "activity":
        screen.hud.grid_remove()
        screen._transcript_card.grid()
        screen._body.grid_rowconfigure(0, weight=0, minsize=0)
        screen._body.grid_rowconfigure(1, weight=1, minsize=0)
    else:
        screen.hud.grid()
        screen._transcript_card.grid()
        screen._body.grid_rowconfigure(0, weight=3, minsize=120)
        screen._body.grid_rowconfigure(1, weight=2, minsize=96)
    screen._focus_btn.config(text={"answer": "Show activity", "activity": "Show answer", "both": "Focus view"}[mode])


def copy_selection(screen):
    if screen.chat.tag_ranges("sel"):
        screen.master.clipboard_clear()
        screen.master.clipboard_append(screen.chat.get("sel.first", "sel.last"))


def build_composer(screen, parent):
    screen._composer = parent
    parent.grid_columnconfigure(0, weight=1)
    content = row(parent)
    content.grid(row=0, column=0, columnspan=2, sticky="ew", padx=14, pady=(9, 4))
    screen._composer_content = content
    screen._manual_entry = tk.Text(content, height=2, wrap="word", undo=True, bd=0, relief="flat", highlightthickness=0,
                                   bg=C["panel"], fg=C["fg2"], insertbackground=C["accent"],
                                   selectbackground="#3e496c", font=("Segoe UI", -round(14 * content._get_widget_scaling())), padx=0, pady=4)
    screen._manual_entry.pack(fill="x")
    screen._input_has_placeholder = True
    screen._manual_entry.insert("1.0", screen.runtime["PLACEHOLDER"])
    def clear_placeholder(_=None):
        if screen._input_has_placeholder:
            screen._manual_entry.delete("1.0", "end")
            screen._manual_entry.config(fg=C["fg"])
            screen._input_has_placeholder = False
    def restore_placeholder(_=None):
        if not screen._manual_entry.get("1.0", "end").strip():
            screen._manual_entry.delete("1.0", "end")
            screen._manual_entry.insert("1.0", screen.runtime["PLACEHOLDER"])
            screen._manual_entry.config(fg=C["fg2"], height=2)
            screen._input_has_placeholder = True
    def paste(_=None):
        clear_placeholder()
        try:
            screen._manual_entry.insert(tk.INSERT, screen.master.clipboard_get())
            resize_input()
        except tk.TclError:
            pass
        return "break"
    def resize_input(_=None):
        count = int(screen._manual_entry.index("end-1c").split(".")[0])
        screen._manual_entry.config(height=min(3 if screen._auto_compact else 5, max(2, count)))
    def newline(_):
        clear_placeholder()
        screen._manual_entry.insert(tk.INSERT, "\n")
        resize_input()
        return "break"
    screen._manual_entry.bind("<FocusIn>", clear_placeholder)
    screen._manual_entry.bind("<FocusOut>", restore_placeholder)
    screen._manual_entry.bind("<KeyPress>", lambda e: clear_placeholder() if e.char and not e.state & 4 else None)
    screen._manual_entry.bind("<KeyRelease>", resize_input)
    screen._manual_entry.bind("<Return>", lambda _: (screen._send_manual(), "break")[1])
    screen._manual_entry.bind("<Control-Return>", lambda _: (screen._send_manual(), "break")[1])
    screen._manual_entry.bind("<Shift-Return>", newline)
    screen._manual_entry.bind("<Control-v>", paste)
    screen._manual_entry.bind("<Control-V>", paste)
    screen._composer_hint = Label(parent, "Enter to ask  ·  Shift+Enter for a new line", size=11, muted=True)
    screen._composer_hint.grid(row=1, column=0, sticky="w", padx=14, pady=(0, 10))
    screen._composer_send = Button(parent, "Ask Copilot  ↑", command=screen._send_manual, primary=True, width=138, height=32)
    screen._composer_send.grid(row=1, column=1, sticky="e", padx=(6, 12), pady=(0, 10))
