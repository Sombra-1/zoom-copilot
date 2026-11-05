"""Quiet release notices in settings and in the workspace."""
from .ui_theme import Button, Label, row, COLORS as C
from .version import APP_VERSION


def sidebar(screen, parent):
    service = getattr(screen.master, "_updates", None)
    screen._update_button = Button(parent, "v" + APP_VERSION + " · Check updates", width=168, height=28,
                                   quiet=True, font=("Segoe UI", 11),
                                   command=lambda: service.check(manual=True) if service else None)
    screen._update_button.grid(row=8, column=0, padx=16, pady=(0, 10), sticky="ew")
    notice(screen, 9, 16)
    if service:
        refresh(screen, service)


def notice(screen, grid_row=8, padx=22):
    strip = row(screen)
    strip.configure(fg_color="#202b35", corner_radius=8)
    screen._update_strip = strip
    screen._update_grid = {"row": grid_row, "column": 0, "sticky": "ew", "padx": padx, "pady": (0, 10)}
    screen._update_label = Label(strip, "", size=11, justify="left", text_color=C["accent"])
    screen._update_label.pack(side="left", padx=10, pady=6)
    compact = grid_row == 9
    if compact:
        screen._update_label.configure(wraplength=140)
        screen._update_label.pack_configure(side="top", anchor="w")
    controls = row(strip)
    controls.pack(side="right" if not compact else "top", padx=4, pady=4)
    Button(controls, "View release", width=86, height=26, quiet=True, font=("Segoe UI", 11),
           command=lambda: screen.master._updates.open_release()).pack(side="left")
    Button(controls, "Later", width=52, height=26, quiet=True, font=("Segoe UI", 11),
           command=lambda: screen.master._updates.dismiss()).pack(side="left")


def refresh(screen, service):
    if screen is None:
        return
    button = getattr(screen, "_update_button", None)
    if button:
        button.configure(text="v" + APP_VERSION + " · " + service.message,
                         state="disabled" if service.busy else "normal")
    if hasattr(screen, "_update_strip"):
        if service.available and service.latest != service.dismissed:
            screen._update_label.configure(text="Update ready: v" + APP_VERSION + " → v" + service.latest)
            screen._update_strip.grid(**screen._update_grid)
        else:
            screen._update_strip.grid_remove()
