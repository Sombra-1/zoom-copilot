"""Desktop setup views. Provider, installation and audio logic stays in the app."""
import tkinter as tk
import customtkinter as ctk

from .ui_theme import COLORS as C, Button, Label, ScrollArea, card, row, entry, select, text_surface
from .support_ui import sidebar_links
from .branding import logo_label, signal_label
from .update_ui import sidebar as update_sidebar


def field(screen, parent, label, key, placeholder="", secret=False):
    outer = row(parent)
    outer.pack(fill="x", pady=7)
    Label(outer, label, muted=True, size=12).pack(anchor="w", pady=(0, 5))
    line = row(outer)
    line.pack(fill="x")
    variable = screen._vars.setdefault(key, tk.StringVar(value=screen.s.get(key, "")))
    widget = entry(line, variable, secret)
    widget.pack(side="left", fill="x", expand=True)
    if secret:
        def toggle_secret():
            visible = bool(widget.cget("show"))
            widget.configure(show="" if visible else "•")
            reveal.config(text="Hide" if visible else "Show")
        reveal = Button(line, "Show", width=52, quiet=True, command=toggle_secret)
        reveal.pack(side="right", padx=(6, 0))
    if placeholder:
        Label(outer, placeholder, size=11, muted=True, wraplength=520, justify="left").pack(anchor="w", pady=(4, 0))
    return widget


def note(parent, text):
    label = Label(parent, text, muted=True, size=12, justify="left", wraplength=500)
    label.pack(fill="x", pady=(4, 9))
    parent.bind("<Configure>", lambda e: label.configure(wraplength=max(180, e.width - 36)), add="+")


def section(parent, title, description=""):
    Label(parent, title, size=17, bold=True).pack(anchor="w", pady=(16, 4))
    if description:
        note(parent, description)


def panel(parent):
    frame = card(parent)
    frame.pack(fill="x", pady=(0, 12))
    inner = row(frame)
    inner.pack(fill="x", padx=18, pady=14)
    return inner


def build(screen, runtime):
    screen.runtime = runtime
    screen.configure(bg=C["bg"])
    screen.grid_columnconfigure(1, weight=1)
    screen.grid_rowconfigure(0, weight=1)
    sidebar = card(screen, width=206, corner_radius=16, fg_color=C["sidebar"])
    sidebar.grid(row=0, column=0, sticky="ns", padx=(14, 0), pady=14)
    sidebar.grid_propagate(False)
    sidebar.grid_rowconfigure(5, weight=1)
    brand = row(sidebar)
    brand.grid(row=0, column=0, padx=19, pady=(20, 3), sticky="w")
    logo_label(brand, size=24).pack(side="left", padx=(0, 7))
    Label(brand, "Zoom Copilot", size=18, bold=True).pack(side="left")
    Label(sidebar, "2.1 PREVIEW", size=11, bold=True, text_color=C["accent"]).grid(
        row=1, column=0, padx=20, pady=(0, 23), sticky="w")
    screen._nav_buttons = {}
    for index, (name, label) in enumerate((("connection", "01  AI connection"), ("audio", "02  Audio & transcript"), ("preferences", "03  Preferences")), 2):
        button = Button(sidebar, label, width=168, height=40, quiet=True, anchor="w",
                        command=lambda target=name: show_page(screen, target))
        button.grid(row=index, column=0, padx=16, pady=4)
        screen._nav_buttons[name] = button
    privacy = card(sidebar, fg_color=C["inset"])
    privacy.grid(row=6, column=0, padx=16, pady=(10, 12), sticky="ew")
    Label(privacy, "You control the context", size=12, bold=True).pack(anchor="w", padx=12, pady=(12, 4))
    Label(privacy, "Choose what to capture.\nVision is always optional.", size=11, muted=True, justify="left").pack(anchor="w", padx=12, pady=(0, 12))
    sidebar_links(sidebar, screen.master)
    update_sidebar(screen, sidebar)
    content = row(screen)
    content.grid(row=0, column=1, sticky="nsew", padx=(20, 20), pady=(14, 14))
    content.grid_columnconfigure(0, weight=1)
    content.grid_rowconfigure(2, weight=1)
    hero = card(content, fg_color=C["elevated"], border_color="#3b4d74", corner_radius=16)
    hero.grid(row=0, column=0, sticky="ew", pady=(0, 14))
    illustration = signal_label(hero)
    if illustration is not None:
        illustration.pack(side="right", padx=(0, 10), pady=2)
    headline = row(hero)
    headline.pack(side="left", fill="x", expand=True, padx=(20, 6), pady=15)
    screen._page_title = Label(headline, "AI connection", size=28, bold=True)
    screen._page_title.pack(anchor="w", pady=(0, 2))
    screen._page_description = Label(headline, "Choose an AI provider for your meetings.", muted=True, size=12,
                                     wraplength=300, justify="left")
    screen._page_description.pack(anchor="w")
    headline.bind("<Configure>", lambda e: screen._page_description.configure(wraplength=max(150, e.width - 10)))
    screen._page_container = row(content)
    screen._page_container.grid(row=2, column=0, sticky="nsew")
    screen._pages = {}
    for name in ("connection", "audio", "preferences"):
        area = ScrollArea(screen._page_container)
        screen._pages[name] = area
    build_connection(screen, screen._pages["connection"].body, runtime)
    build_audio(screen, screen._pages["audio"].body, runtime)
    build_preferences(screen, screen._pages["preferences"].body)
    # A required transcription/AI key remains outside the tabbed panels.
    screen._groq_key_frame = card(content)
    screen._groq_key_frame.grid(row=3, column=0, sticky="ew", pady=(10, 0))
    key_inner = row(screen._groq_key_frame)
    key_inner.pack(fill="x", padx=16, pady=9)
    screen._groq_key_reason = Label(key_inner, "", muted=True, size=11)
    screen._groq_key_reason.pack(anchor="w")
    field(screen, key_inner, "Groq API key", "groq_key", secret=True)
    footer = row(content)
    footer.grid(row=4, column=0, sticky="ew", pady=(14, 0))
    screen._status = Label(footer, "Ready when you are.", size=12, muted=True, wraplength=470, justify="left")
    screen._status.pack(fill="x", pady=(0, 9))
    screen._test_btn = Button(footer, "Test connection", command=screen._test, width=142)
    screen._test_btn.pack(side="left")
    Button(footer, "Open workspace  →", command=screen._launch, primary=True, width=190, height=38).pack(side="right")
    screen._refresh()
    screen._refresh_transcription()
    screen._refresh_interview_mode()
    show_page(screen, "connection")


def show_page(screen, name):
    for key, page in screen._pages.items():
        page.pack_forget()
        screen._nav_buttons[key].config(bg=C["panel2"] if key == name else "transparent",
                                        fg=C["fg"] if key == name else C["fg2"])
    screen._pages[name].pack(fill="both", expand=True)
    title, description = {
        "connection": ("AI connection", "Choose a provider for meeting questions and notes."),
        "audio": ("Audio & transcript", "Select the audio input and where speech is decoded."),
        "preferences": ("Preferences", "Adjust the overlay, answers, and screen context."),
    }[name]
    screen._page_title.config(text=title)
    screen._page_description.config(text=description)
    screen._active_page = name


def build_connection(screen, parent, runtime):
    screen._backend_section = parent
    chooser = panel(parent)
    Label(chooser, "AI provider", size=15, bold=True).pack(anchor="w", pady=(0, 12))
    screen._vars["backend"] = tk.StringVar(value=screen.s["backend"])
    choices = row(chooser)
    choices.pack(fill="x")
    for col in range(3):
        choices.grid_columnconfigure(col, weight=1, uniform="providers")
    labels = {"codex": ("Codex / ChatGPT", "Your connected account"), "builtin": ("Built-in AI", "Local · no account"),
              "ollama": ("Ollama", "Your model & server"), "groq": ("Groq", "Fast cloud inference"),
              "claude": ("Claude", "Anthropic API"), "demo": ("Demo", "Preview the workspace")}
    screen._provider_cards = {}
    for index, name in enumerate(("codex", "builtin", "ollama", "groq", "claude", "demo")):
        title, subtitle = labels[name]
        button = Button(choices, title + "\n" + subtitle, width=120, height=60, anchor="w",
                        border_width=1, border_color=C["border"], font=("Segoe UI", 12),
                        command=lambda value=name: choose_backend(screen, value))
        button._text_label.configure(justify="left")
        button.grid(row=index // 3, column=index % 3, sticky="ew", padx=(0, 7), pady=(0, 7))
        screen._provider_cards[name] = button
    screen._backend_container = row(parent)
    screen._backend_container.pack(fill="x")
    for attribute in ("_bif", "_df", "_of", "_cf", "_gf", "_cxf"):
        setattr(screen, attribute, row(screen._backend_container))
    section(screen._cxf, "Codex, connected in the background", "Uses your existing Codex CLI sign-in. The desktop Codex app stays closed.")
    screen._cx_status = Label(screen._cxf, "Checking your connection…", size=12, muted=True, justify="left", wraplength=500)
    screen._cx_status.pack(fill="x", pady=8)
    Button(screen._cxf, "Refresh status", command=screen._check_codex, width=132).pack(anchor="w", pady=(0, 10))
    field(screen, screen._cxf, "Model", "codex_model", "Leave empty to use your account's default model.")
    field(screen, screen._cxf, "Codex CLI path", "codex_path", "Leave empty to discover the installed CLI automatically.")
    note(screen._cxf, "Need to sign in? Run codex login in a terminal, then refresh status.")
    section(screen._bif, "Local by default", "Ollama and a small local model. No API account required.")
    screen._bi_status = Label(screen._bif, "Check or install the local model.", muted=True)
    screen._bi_status.pack(anchor="w", pady=8)
    screen._bi_btn = Button(screen._bif, "Set up built-in AI", command=screen._setup_builtin, width=170)
    screen._bi_btn.pack(anchor="w")
    screen._bi_progress = Label(screen._bif, "", size=12, muted=True, wraplength=500, justify="left")
    screen._bi_progress.pack(fill="x", pady=8)
    section(screen._df, "Take a look around", "Demo responses let you try the interface without sending data to an AI provider.")
    section(screen._of, "Your Ollama server")
    field(screen, screen._of, "Server address", "ollama_host")
    field(screen, screen._of, "Model", "ollama_model")
    section(screen._cf, "Anthropic connection")
    field(screen, screen._cf, "API key", "anthropic_key", secret=True)
    field(screen, screen._cf, "Model", "claude_model")
    section(screen._gf, "Fast cloud answers")
    screen._vars["groq_model"] = tk.StringVar(value=screen.s["groq_model"])
    select(screen._gf, screen._vars["groq_model"], runtime["GROQ_AI_MODELS"], width=290).pack(anchor="w", pady=10)


def choose_backend(screen, name):
    screen._vars["backend"].set(name)
    screen._refresh()


def refresh_provider(screen):
    selected = screen._vars["backend"].get()
    for name, button in screen._provider_cards.items():
        button.configure(fg_color="#29375c" if name == selected else C["inset"],
                         border_color="#8698ff" if name == selected else C["border"],
                         text_color=C["fg"] if name == selected else C["fg2"])


def refresh_credentials(screen):
    needed = screen._vars["backend"].get() == "groq" or screen._vars["transcription"].get() == "groq"
    if needed:
        screen._groq_key_frame.grid()
        screen._groq_key_reason.config(text="Required for " + ("Groq AI and transcription" if screen._vars["backend"].get() == "groq" and screen._vars["transcription"].get() == "groq" else "your Groq cloud selection"))
    else:
        screen._groq_key_frame.grid_remove()


def build_audio(screen, parent, runtime):
    provider = panel(parent)
    Label(provider, "Transcription", size=15, bold=True).pack(anchor="w", pady=(0, 12))
    screen._vars["transcription"] = tk.StringVar(value=screen.s["transcription"])
    for name, title in (("local", "Local Whisper · stays on this computer"), ("groq", "Groq Whisper · cloud transcription")):
        ctk.CTkRadioButton(provider, text=title, variable=screen._vars["transcription"], value=name,
                           command=screen._refresh_transcription, fg_color=C["accent2"], hover_color=C["accent"],
                           border_color=C["border2"], text_color=C["fg"], font=("Segoe UI", 13)).pack(anchor="w", pady=6)
    screen._groq_tr_frame, screen._local_tr_frame = row(provider), row(provider)
    screen._vars["whisper_model"] = tk.StringVar(value=screen.s["whisper_model"])
    select(screen._groq_tr_frame, screen._vars["whisper_model"], runtime["WHISPER_MODELS"], width=290).pack(anchor="w", pady=12)
    build_whisper_table(screen, screen._local_tr_frame, runtime)
    device = panel(parent)
    Label(device, "Audio input", size=15, bold=True).pack(anchor="w")
    field(screen, device, "Device name", "device_name")
    buttons = row(device)
    buttons.pack(fill="x", pady=5)
    windows = runtime["sys"].platform == "win32"
    Button(buttons, "Choose device", command=screen._discover_windows_devices if windows else screen._discover_linux_sources, width=132).pack(side="left", padx=(0, 7))
    screen._win_auto_btn = Button(buttons, "Auto-detect", command=screen._autodetect_windows_device, width=116)
    if windows:
        screen._win_auto_btn.pack(side="left")
    screen._win_dev_status = Label(device, "Capture your meeting's speaker output, rather than room audio.", muted=True, size=11, wraplength=500)
    screen._win_dev_status.pack(fill="x", pady=5)
    screen._linux_dev_status = screen._win_dev_status
    test = row(device)
    test.pack(fill="x", pady=8)
    screen._mic_btn = Button(test, "Test audio", command=screen._test_mic, width=112)
    screen._mic_btn.pack(side="left", padx=(0, 12))
    screen._vol_canvas = tk.Canvas(test, width=160, height=14, bg=C["input_bg"], bd=0, highlightthickness=0)
    screen._vol_bar = screen._vol_canvas.create_rectangle(0, 0, 0, 14, fill=C["success"], outline="")
    screen._mic_status = Label(device, "Play something in your meeting app, then test.", muted=True, size=12, wraplength=500)
    screen._mic_status.pack(fill="x", pady=5)
    field(screen, device, "Language", "language", "Language code, for example en, ar, fr, or de.")
    field(screen, device, "Audio chunk length", "chunk_seconds", "Seconds per transcription chunk · 2–30.")


def build_whisper_table(screen, parent, runtime):
    install = row(parent)
    install.pack(fill="x", pady=(14, 8))
    screen._fw_status = Label(install, "", size=11, muted=True)
    screen._fw_status.pack(side="left")
    screen._fw_btn = Button(install, "Install Whisper", command=screen._install_local_whisper, width=125, height=30)
    screen._fw_btn.pack(side="right")
    screen._vars["local_whisper_model"] = tk.StringVar(value=screen.s["local_whisper_model"])
    screen._model_row_widgets = {}
    for name, size in zip(runtime["LOCAL_WHISPER_MODELS"], ("40 MB", "150 MB", "500 MB", "1.5 GB", "3 GB")):
        line = row(parent)
        line.pack(fill="x", pady=4)
        ctk.CTkRadioButton(line, text=name, width=110, variable=screen._vars["local_whisper_model"], value=name,
                           fg_color=C["accent2"], border_color=C["border2"], font=("Segoe UI", 12)).pack(side="left")
        Label(line, size, width=65, size=11, muted=True).pack(side="left")
        status = Label(line, "", size=11, muted=True)
        status.pack(side="left", fill="x", expand=True)
        delete = Button(line, "Delete", command=lambda model=name: screen._delete_model(model), width=58, height=28, quiet=True)
        delete.pack(side="right")
        install = Button(line, "Get", command=lambda model=name: screen._download_model(model), width=54, height=28)
        install.pack(side="right", padx=5)
        screen._model_row_widgets[name] = status, install, delete
    screen._check_local_whisper_status()


def build_preferences(screen, parent):
    appearance = panel(parent)
    Label(appearance, "Answer appearance", size=15, bold=True).pack(anchor="w", pady=(0, 10))
    screen._vars["answer_detail"] = tk.StringVar(value=screen.s["answer_detail"])
    select(appearance, screen._vars["answer_detail"], ("compact", "normal", "detailed")).pack(anchor="w")
    field(screen, appearance, "Answer font size", "answer_font_size", "9–24 px. You can also adjust this in the workspace.")
    field(screen, appearance, "Default opacity", "opacity", "0.3–1.0. Use 1.0 for a fully opaque, easy-to-read workspace.")
    assistance = panel(parent)
    Label(assistance, "Meeting assistance", size=15, bold=True).pack(anchor="w", pady=(0, 10))
    for key, text in (("presentation_mode", "Short presentation talking points"), ("developer_mode", "Project developer tools"), ("interview_mode", "Practice / permitted accessibility assistance")):
        screen._vars[key] = tk.BooleanVar(value=screen.s.get(key, False))
        ctk.CTkSwitch(assistance, text=text, variable=screen._vars[key], fg_color=C["border2"], progress_color=C["accent2"],
                      font=("Segoe UI", 12), command=screen._refresh_interview_mode if key == "interview_mode" else None).pack(anchor="w", pady=9)
    screen._im_frame = row(assistance)
    for attribute, key, label in (("_im_bg_text", "interview_background", "Your real background"), ("_im_role_text", "interview_role", "Role and context")):
        Label(screen._im_frame, label, size=12, muted=True).pack(anchor="w", pady=(8, 3))
        wrapper, text = text_surface(screen._im_frame, height=4)
        wrapper.pack(fill="x")
        text.insert("1.0", screen.s.get(key, ""))
        setattr(screen, attribute, text)
    field(screen, assistance, "Smart-trigger keywords", "custom_keywords", "Comma-separated project terms or phrases worth catching.")
    field(screen, assistance, "Screen-watch interval", "screen_interval", "3–300 seconds. Vision is enabled separately in the workspace.")
