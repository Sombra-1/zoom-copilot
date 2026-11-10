"""Shared desktop design tokens and a small Tk-compatible modern widget layer."""
import tkinter as tk
import customtkinter as ctk

COLORS = {
    "bg": "#0b101a", "panel": "#151e2e", "panel2": "#202c43",
    "elevated": "#192540", "inset": "#101827", "sidebar": "#121a2b",
    "border": "#2b3a55", "border2": "#455777", "accent": "#aebfff",
    "accent2": "#625ee5", "accent3": "#a9a1ff", "them": "#d6e0f0",
    "ai": "#eaf0ff", "error": "#ff9bab", "success": "#89e1c2",
    "warn": "#f2ca91", "fg": "#f3f6ff", "fg2": "#a8b6cf",
    "btn_hover": "#304261", "input_bg": "#101827", "input_fg": "#edf2ff",
}
FONT = "Segoe UI"


def configure_theme():
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")


def _translate(options):
    mapped = {}
    for name, value in options.items():
        if name in ("activeforeground", "relief", "bd", "cursor", "padx", "pady"):
            continue
        mapped[{"bg": "fg_color", "fg": "text_color", "activebackground": "hover_color"}.get(name, name)] = value
    return mapped


class Button(ctk.CTkButton):
    """Accept the existing controller's .config(bg=..., fg=...) updates."""
    def __init__(self, parent, text="", command=None, primary=False, quiet=False, **kwargs):
        defaults = dict(width=100, height=34, corner_radius=9, border_width=0 if quiet else 1,
                        border_color="#9695ff" if primary else COLORS["border"],
                        fg_color=COLORS["accent2"] if primary else ("transparent" if quiet else COLORS["panel2"]),
                        hover_color="#7774ef" if primary else COLORS["btn_hover"],
                        text_color="#ffffff" if primary else COLORS["fg"],
                        font=(FONT, 13), anchor="center")
        defaults.update(kwargs)
        super().__init__(parent, text=text, command=command, **defaults)

    def config(self, **kwargs):
        return self.configure(**_translate(kwargs))

    def cget(self, attribute_name):
        return super().cget({"bg": "fg_color", "fg": "text_color"}.get(attribute_name, attribute_name))


class Label(ctk.CTkLabel):
    def __init__(self, parent, text="", size=13, muted=False, bold=False, **kwargs):
        defaults = dict(font=(FONT, size, "bold" if bold else "normal"),
                        text_color=COLORS["fg2"] if muted else COLORS["fg"], anchor="w", height=22)
        defaults.update(kwargs)
        super().__init__(parent, text=text, **defaults)

    def config(self, **kwargs):
        return self.configure(**_translate(kwargs))

    def cget(self, attribute_name):
        return super().cget({"fg": "text_color", "bg": "fg_color"}.get(attribute_name, attribute_name))


def card(parent, **kwargs):
    options = dict(fg_color=COLORS["panel"], border_color=COLORS["border"], border_width=1, corner_radius=15)
    options.update(kwargs)
    return ctk.CTkFrame(parent, **options)


def row(parent, **kwargs):
    kwargs.setdefault("fg_color", "transparent")
    return ctk.CTkFrame(parent, **kwargs)


def entry(parent, variable, secret=False, width=260):
    return ctk.CTkEntry(parent, textvariable=variable, show="•" if secret else "", width=width,
                        height=36, corner_radius=8, fg_color=COLORS["input_bg"],
                        border_color=COLORS["border"], border_width=1, text_color=COLORS["fg"], font=(FONT, 13))


def select(parent, variable, values, command=None, width=150):
    return ctk.CTkOptionMenu(parent, variable=variable, values=list(values), command=command,
                             width=width, height=34, corner_radius=8, fg_color=COLORS["panel2"],
                             button_color=COLORS["panel2"], button_hover_color=COLORS["btn_hover"],
                             dropdown_fg_color=COLORS["panel2"], dropdown_hover_color=COLORS["btn_hover"],
                             text_color=COLORS["fg"], font=(FONT, 13), dropdown_font=(FONT, 13))


def text_surface(parent, height=5, **kwargs):
    """Keep Tk's rich-text API for selection, math images and syntax tags."""
    wrapper = row(parent, fg_color=COLORS["inset"], corner_radius=8)
    scale = wrapper._get_widget_scaling()
    text = tk.Text(wrapper, height=height, bg=COLORS["inset"], fg=COLORS["fg"],
                   insertbackground=COLORS["accent"], relief="flat", bd=0,
                   highlightthickness=0, selectbackground="#3e496c", wrap="word",
                   font=(FONT, -round(14 * scale)), padx=6, pady=6, **kwargs)
    scrollbar = ctk.CTkScrollbar(wrapper, command=text.yview, width=10,
                                 fg_color="transparent", button_color=COLORS["border2"],
                                 button_hover_color=COLORS["fg2"])
    text.configure(yscrollcommand=scrollbar.set)
    scrollbar.pack(side="right", fill="y", padx=(4, 0))
    text.pack(fill="both", expand=True, padx=(4, 0), pady=2)
    return wrapper, text


class ScrollArea(ctk.CTkFrame):
    """A scroll area whose wheel binding is scoped and removed on destruction."""
    def __init__(self, parent):
        super().__init__(parent, fg_color="transparent")
        self.canvas = tk.Canvas(self, bg=COLORS["bg"], bd=0, highlightthickness=0)
        scrollbar = ctk.CTkScrollbar(self, command=self.canvas.yview, width=10,
                                     fg_color="transparent", button_color=COLORS["border2"])
        self.canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.body = row(self.canvas)
        self._window = self.canvas.create_window((0, 0), anchor="nw", window=self.body)
        self.body.bind("<Configure>", lambda _: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self._window, width=e.width))
        self._wheel_root = self.winfo_toplevel()
        self._wheel_ids = [(sequence, self._wheel_root.bind(sequence, self._wheel, add="+"))
                           for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>")]

    def _wheel(self, event):
        widget = event.widget
        if isinstance(widget, tk.Text):
            return
        try:
            while widget is not self and widget is not self._wheel_root:
                widget = widget.master
            if widget is not self:
                return
            delta = (-1 if event.num == 4 else 1) if getattr(event, "num", None) in (4, 5) else int(-event.delta / 120)
            if self.body.winfo_height() > self.canvas.winfo_height():
                self.canvas.yview_scroll(delta, "units")
                return "break"
        except (AttributeError, tk.TclError):
            return

    def destroy(self):
        for sequence, function_id in self._wheel_ids:
            self._wheel_root.unbind(sequence, function_id)
        super().destroy()


def fit_window(root, width, height, minimum=(700, 560)):
    """Use logical dimensions while keeping high-DPI windows inside the display."""
    scale = root._get_window_scaling() if isinstance(root, ctk.CTk) else 1.0
    available_w = int(root.winfo_screenwidth() * .94 / scale)
    available_h = int(root.winfo_screenheight() * .91 / scale)
    root.minsize(min(minimum[0], available_w), min(minimum[1], available_h))
    root.geometry(f"{min(width, available_w)}x{min(height, available_h)}+60+45")


def destroy_root(root):
    """Cancel interpreter timers before deleting their registered Tcl commands."""
    for timer in root.tk.call("after", "info"):
        # Each callback command belongs to the widget that scheduled it.
        # Leave command cleanup to that widget's destroy(), rather than
        # deleting child commands through root.after_cancel().
        root.tk.call("after", "cancel", timer)
    root.destroy()
