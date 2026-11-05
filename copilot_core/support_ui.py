"""Small support controls matching the desktop's existing theme."""
from .community import support_action
from .ui_theme import Button, Label, row, COLORS as C


def sidebar_links(sidebar, root):
    links = row(sidebar)
    links.grid(row=7, column=0, sticky="ew", padx=16, pady=(0, 16))
    Button(links, "★  Star on GitHub", width=168, height=30,
           command=lambda: support_action(root, "star")).pack(fill="x", pady=(0, 4))
    Button(links, "Support on Patreon", width=168, height=28, quiet=True,
           command=lambda: support_action(root, "donate")).pack(fill="x")


def workspace_links(screen):
    strip = row(screen)
    strip.grid(row=7, column=0, sticky="ew", padx=22, pady=(0, 10))
    screen._support_strip = strip
    screen._support_label = Label(strip, "Built by Sombra-1 · open source", size=11, muted=True)
    screen._support_label.pack(side="left", padx=8, pady=3)
    screen._support_dismiss = Button(strip, "Dismiss", width=64, height=28, quiet=True, font=("Segoe UI", 11),
                                    command=lambda: screen.master._community.dismiss())
    screen._support_star = Button(strip, "★  Star on GitHub", width=118, height=28, quiet=True,
                                 font=("Segoe UI", 11), command=lambda: support_action(screen.master, "star"))
    screen._support_star.pack(side="right", padx=3, pady=3)
    screen._support_donate = Button(strip, "Support on Patreon", width=124, height=28, quiet=True,
                                   font=("Segoe UI", 11), command=lambda: support_action(screen.master, "donate"))
    screen._support_donate.pack(side="right", padx=3, pady=3)


def show_reminder(screen, visible):
    if visible:
        screen._support_strip.configure(fg_color="#291e23", corner_radius=8, border_width=1, border_color="#80505b")
        screen._support_label.config(text="KEEP THE CODE FREE.\nBack the dev, choom.", fg="#f2d38b", justify="left")
        screen._support_dismiss.pack(side="right", padx=3, pady=3)
        screen._support_donate.configure(text_color="#f2d38b")
    else:
        screen._support_strip.configure(fg_color="transparent", border_width=0)
        screen._support_label.config(text="Built by Sombra-1 · open source", fg=C["fg2"])
        screen._support_dismiss.pack_forget()
        screen._support_donate.configure(text_color=C["fg"])
