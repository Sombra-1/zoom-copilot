"""Small Tk answer HUD with offline math, code, history and local disclosure."""
import io
import re
import threading
import customtkinter as ctk
from .ui_theme import Button, Label, row, text_surface

from .answer_schema import parse_answer
from .math_renderer import MathRenderer


def answer_blocks(answer, detail="compact"):
    """Pure presentation plan shared by widget code and unit tests."""
    answer = parse_answer(answer)
    blocks = [("title", answer.title)]
    if answer.summary:
        blocks.append(("text", answer.summary))
    if answer.latex:
        blocks.append(("math", answer.latex))
    elif answer.final_answer and answer.final_answer != answer.summary:
        blocks.append(("text", answer.final_answer))
    for value in answer.bullets:
        blocks.append(("bullet", value))
    if detail != "compact":
        for key in ("error", "cause", "fix"):
            if getattr(answer, key):
                blocks.append(("heading", key.title()))
                blocks.append(("text", getattr(answer, key)))
        if answer.code:
            blocks.append(("code:" + answer.language, answer.code))
        if answer.content and answer.content != answer.summary:
            blocks.append(("markdown", answer.content))
    if detail == "detailed":
        for index, step in enumerate(answer.steps, 1):
            blocks.append(("math" if answer.type == "math" else "text",
                           step if answer.type == "math" else f"{index}. {step}"))
        if answer.explanation:
            blocks.extend([("heading", "Explanation"), ("markdown", answer.explanation)])
    if answer.next_sentence:
        blocks.extend([("heading", "Suggested next sentence"), ("text", answer.next_sentence)])
    return blocks


class AnswerHud(ctk.CTkFrame):
    def __init__(self, parent, settings, colors, dispatcher):
        self.colors, self.settings, self.dispatcher = colors, settings, dispatcher
        super().__init__(parent, fg_color=colors.get("elevated", colors["panel"]), border_width=1,
                         border_color=colors["border2"], corner_radius=15)
        self.answers, self.index, self.pinned = [], -1, False
        self.detail = settings.get("answer_detail", "compact")
        self.font_size = settings.get("answer_font_size", 12)
        self.renderer = MathRenderer()
        self._revision = 0
        self._images = []
        self._closed = False
        self._rendering = False
        self._reflow_id = None
        self._last_math_width = 0
        bar = row(self)
        bar.pack(fill="x", padx=16, pady=(11, 3))
        Label(bar, "Copilot answer", size=12, bold=True, text_color=colors["accent"]).pack(side="left")
        self._buttons = {}
        for label, command, width in (("Clear", self.clear, 48), ("Copy", self.copy, 48),
                                      ("Pin", self.pin, 46), ("›", lambda: self.move(1), 28),
                                      ("‹", lambda: self.move(-1), 28)):
            button = Button(bar, label, command=command, width=width, height=27, quiet=True, font=("Segoe UI", 11))
            button.pack(side="right", padx=1)
            self._buttons[label] = button
        self.position = Label(bar, "", size=11, muted=True)
        self.position.pack(side="right", padx=8)
        footer = row(self)
        footer.pack(side="bottom", fill="x", padx=14, pady=(4, 10))
        for label in ("Compact", "Normal", "Detailed"):
            button = Button(footer, label, command=lambda value=label.lower(): self.set_detail(value),
                            width=68, height=27, quiet=True, font=("Segoe UI", 11))
            button.pack(side="left", padx=1)
            self._buttons[label] = button
        for label, command in (("+", lambda: self.resize(1)), ("−", lambda: self.resize(-1)), ("Expand", self.toggle)):
            button = Button(footer, label, command=command, width=100 if label == "Expand" else 28,
                            height=27, quiet=True, font=("Segoe UI", 11))
            button.pack(side="right", padx=1)
            self._buttons[label] = button
        wrapper, self.text = text_surface(self, height=4, state="disabled")
        wrapper.pack(fill="both", expand=True, padx=18, pady=(4, 5))
        self.text.configure(spacing1=3, spacing3=5)
        self.text.tag_config("heading", foreground=colors["accent"], spacing1=9)
        self.text.tag_config("title", foreground=colors["fg"], spacing3=10)
        self.text.tag_config("bullet", lmargin1=3, lmargin2=19, spacing3=6)
        self.text.tag_config("code", background=colors["input_bg"], spacing1=4, spacing3=4)
        self.text.tag_config("math_fallback", foreground=colors["warn"])
        self.text.tag_config("inline_code", background=colors["panel2"], foreground=colors["accent"])
        self.text.tag_config("bold", foreground=colors["fg"])
        self.bind("<Configure>", self._on_resize, add="+")
        self.render()

    def add(self, raw):
        self.answers.append(parse_answer(raw))
        if len(self.answers) > 50:
            if self.pinned and self.index == 0:
                self.answers.pop(1)
            else:
                self.answers.pop(0)
                self.index = max(0, self.index - 1)
        if not self.pinned or self.index < 0:
            self.index = len(self.answers) - 1
        self.render()

    def move(self, delta):
        if self.answers:
            self.index = max(0, min(len(self.answers) - 1, self.index + delta))
            self.render()

    def set_detail(self, detail):
        self.detail = detail if detail in ("compact", "normal", "detailed") else "compact"
        self.settings["answer_detail"] = self.detail
        self.render()

    def toggle(self):
        self.set_detail("detailed" if self.detail == "compact" else "compact")

    def pin(self):
        self.pinned = not self.pinned
        self._buttons["Pin"].config(text="Pinned" if self.pinned else "Pin")

    def copy(self):
        if self.answers:
            self.clipboard_clear()
            self.clipboard_append(self.answers[self.index].markdown())

    def resize(self, delta):
        self.font_size = max(9, min(24, self.font_size + delta))
        self.settings["answer_font_size"] = self.font_size
        self.render()

    def clear(self):
        self.answers.clear()
        self.index = -1
        self.render()

    def _code(self, value, language=""):
        self.text.insert("end", (language or "Code") + "\n", "heading")
        try:
            from pygments import lex
            from pygments.lexers import get_lexer_by_name, guess_lexer
            lexer = get_lexer_by_name(language) if language else guess_lexer(value)
            from pygments.styles import get_style_by_name
            style = get_style_by_name("monokai")
            for token, content in lex(value[:16000], lexer):
                name = "syntax_" + str(token)
                color = style.style_for_token(token).get("color")
                self.text.tag_config(name, foreground="#" + color if color else self.colors["fg"])
                self.text.insert("end", content, ("code", name))
        except Exception:
            self.text.insert("end", value, "code")
        self.text.insert("end", "\n")

    def _markdown(self, value):
        # Deliberately no HTML/browser execution. Fenced code and display math
        # receive dedicated rendering; ordinary Markdown is safe styled text.
        pieces = re.split(r"(```[\s\S]*?```|\$\$[\s\S]*?\$\$|\\\[[\s\S]*?\\\])", value)
        for piece in pieces:
            if piece.startswith("```"):
                header, _, code = piece[3:-3].partition("\n")
                self._code(code, header.strip())
            elif piece.startswith(("$$", r"\[")):
                self._equation(piece[2:-2])
            else:
                for line in piece.splitlines():
                    if line.startswith("#"):
                        self.text.insert("end", line.lstrip("# ") + "\n", "heading")
                    else:
                        if line.lstrip().startswith(("- ", "* ")):
                            self.text.insert("end", "• ", "bullet")
                            line = line.lstrip()[2:]
                        self._inline(line)
                        self.text.insert("end", "\n")

    def _inline(self, value):
        for piece in re.split(r"(\*\*[^*]+\*\*|`[^`]+`)", value):
            if piece.startswith("**") and piece.endswith("**"):
                self.text.insert("end", piece[2:-2], "bold")
            elif piece.startswith("`") and piece.endswith("`"):
                self.text.insert("end", piece[1:-1], "inline_code")
            else:
                self.text.insert("end", piece)

    def _on_resize(self, event):
        if self._closed or abs(event.width - self._last_math_width) < 50:
            return
        if self._reflow_id:
            self.after_cancel(self._reflow_id)
        def reflow():
            self._reflow_id = None
            if not self._closed and self._equations:
                self.render()
        self._reflow_id = self.after(180, reflow)

    def _equation(self, equation):
        key = "math_" + str(len(self._equations))
        self.text.mark_set(key, "end-1c")
        self.text.mark_gravity(key, "left")
        self.text.insert("end", "Rendering equation…\n", ("math_fallback", key))
        self._equations.append((key, equation.strip().strip("$")))

    def render(self):
        self._revision += 1
        self._images.clear()
        self._equations = []
        scale = self._get_widget_scaling()
        pixels = max(10, round(self.font_size * scale))
        self.text.config(state="normal", height={"compact": 3, "normal": 4, "detailed": 5}[self.detail],
                         font=("Segoe UI", -pixels))
        self.text.tag_config("title", font=("Segoe UI", -(pixels + 5), "bold"))
        self.text.tag_config("bold", font=("Segoe UI", -pixels, "bold"))
        self.text.tag_config("code", font=("Consolas", -pixels))
        self.text.tag_config("inline_code", font=("Consolas", -pixels))
        self.text.tag_config("empty_title", font=("Segoe UI", -round(23 * scale), "bold"), spacing3=14)
        self.text.tag_config("empty_hint", foreground=self.colors["fg2"], font=("Segoe UI", -round(13 * scale)))
        self.text.delete("1.0", "end")
        self.position.config(text=f"{self.index + 1}/{len(self.answers)}" if self.answers else "")
        for level in ("compact", "normal", "detailed"):
            self._buttons[level.title()].config(fg=self.colors["accent"] if self.detail == level else self.colors["fg2"])
        self._buttons["Expand"].config(text="Show details" if self.detail == "compact" else "Collapse")
        for key in ("Pin", "Copy", "Expand", "Clear", "‹", "›"):
            self._buttons[key].config(state="normal" if self.answers else "disabled")
        if not self.answers:
            self.text.insert("end", "A little clarity,\nright when you need it.\n", "empty_title")
            self.text.insert("end", "Ask a question below, or start listening to your meeting.\nYour answers, solutions, and talking points appear here.", "empty_hint")
        else:
            for kind, value in answer_blocks(self.answers[self.index], self.detail):
                if kind == "math":
                    self._equation(value)
                elif kind.startswith("code:"):
                    self._code(value, kind[5:])
                elif kind == "markdown":
                    self._markdown(value)
                else:
                    self.text.insert("end", ("• " if kind == "bullet" else "") + value + "\n", kind)
        self.text.config(state="disabled")
        self._render_math()

    def _render_math(self):
        if not self._equations or self._rendering or self._closed:
            return
        equations, revision = list(self._equations), self._revision
        self._last_math_width = self.winfo_width()
        font, width = round((self.font_size + 5) * self._get_widget_scaling()), max(220, self.winfo_width() - 55)
        self._rendering = True
        def worker():
            try:
                images = self.renderer.render([eq for _, eq in equations], font, width)
            except Exception:
                images = []
            def apply():
                self._rendering = False
                if self._closed:
                    return
                if self._revision != revision:
                    self._render_math()
                    return
                self.text.config(state="normal")
                # Replace from bottom to top so deleting a placeholder cannot
                # collapse a later equation's insertion point onto this one.
                for index in reversed(range(len(equations))):
                    mark, equation = equations[index]
                    spans = self.text.tag_ranges(mark)
                    if not spans:
                        continue
                    position = str(spans[0])
                    self.text.delete(spans[0], spans[-1])
                    blob = images[index] if index < len(images) else None
                    if blob:
                        try:
                            from PIL import Image, ImageTk
                            photo = ImageTk.PhotoImage(Image.open(io.BytesIO(blob)))
                            self._images.append(photo)
                            self.text.image_create(position, image=photo)
                        except Exception:
                            blob = None
                    if not blob:
                        self.text.insert(position, equation + "\n[LaTeX preview unavailable; see CODEX.md]\n", "math_fallback")
                    else:
                        self.text.insert(position + " +1c", "\n")
                self.text.config(state="disabled")
            self.dispatcher.post(apply)
        threading.Thread(target=worker, daemon=True).start()

    def close(self):
        if self._closed:
            return
        self._closed = True
        if self._reflow_id:
            self.after_cancel(self._reflow_id)
            self._reflow_id = None
        self.renderer.close()

    def destroy(self):
        self.close()
        super().destroy()
