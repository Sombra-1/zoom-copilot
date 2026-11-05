"""Reviewable UI for source diagnostics; no model-controlled local execution."""
import hashlib
import json
import threading
import tkinter as tk
from tkinter import scrolledtext

from .codex_backend import SERVICE
from .debug_agent import DebugAgent, redact


class DebugPanel(tk.Toplevel):
    def __init__(self, root, settings, dispatcher, repository, errors):
        super().__init__(root)
        self.title("Zoom Copilot development tools")
        self.geometry("760x620")
        self.settings, self.dispatcher = settings, dispatcher
        self.agent = DebugAgent(repository, settings.get("developer_mode", False))
        self.proposal = None
        self._alive = threading.Event()
        self._alive.set()
        self._busy = False
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.file = tk.StringVar(value="zoom_copilot.py")
        tk.Label(self, text="Selected source + entered issue may be sent to Codex Cloud only when you click Propose.\n"
                 "Checks run locally. Review the full diff before approving a code change.", justify="left").pack(anchor="w", padx=12, pady=8)
        row = tk.Frame(self)
        row.pack(fill="x", padx=12)
        tk.OptionMenu(row, self.file, *self.agent.files()).pack(side="left")
        tk.Button(row, text="Inspect", command=self.inspect).pack(side="left")
        for label, check in (("Run tests", "tests"), ("Lint", "lint"), ("Security", "security")):
            tk.Button(row, text=label, command=lambda name=check: self.run_check(name)).pack(side="left")
        self.issue = scrolledtext.ScrolledText(self, height=5, wrap="word")
        self.issue.pack(fill="x", padx=12, pady=8)
        self.issue.insert("1.0", redact("\n".join(errors[-4:])) or "Describe the Zoom Copilot bug to investigate.")
        buttons = tk.Frame(self)
        buttons.pack(fill="x", padx=12)
        tk.Button(buttons, text="Propose fix with Codex", command=self.propose).pack(side="left")
        self.approve_button = tk.Button(buttons, text="Approve displayed diff + run tests", command=self.approve, state="disabled")
        self.approve_button.pack(side="left", padx=5)
        tk.Button(buttons, text="Reject", command=self.reject).pack(side="left")
        self.output = scrolledtext.ScrolledText(self, wrap="none", font=("Consolas", 10))
        self.output.pack(fill="both", expand=True, padx=12, pady=10)

    def destroy(self):
        self._alive.clear()
        self.agent.close()
        super().destroy()

    def show(self, text):
        self.output.delete("1.0", "end")
        self.output.insert("1.0", text)

    def inspect(self):
        self.reject()
        self.show(self.agent.inspect(self.file.get()))

    def reject(self):
        self.proposal = None
        self.approve_button.config(state="disabled")

    def _run(self, operation, apply):
        if self._busy:
            return
        self._busy = True
        self.show("Working…")
        def worker():
            try:
                result = operation()
                error = None
            except Exception as exc:
                result, error = None, redact(str(exc))
            def finish():
                self._busy = False
                if self._alive.is_set():
                    self.show(error) if error else apply(result)
            self.dispatcher.post(finish)
        threading.Thread(target=worker, daemon=True).start()

    def run_check(self, name):
        self.reject()
        self._run(lambda: self.agent.check(name), lambda result: self.show(f"Exit {result[0]}\n{result[1]}"))

    def propose(self):
        self.reject()
        relative = self.file.get()
        source = self.agent.inspect(relative)
        issue = redact(self.issue.get("1.0", "end"))
        original_hash = hashlib.sha256(self.agent.source_path(relative).read_bytes()).hexdigest()
        prompt = ("Investigate only the supplied Zoom Copilot source and issue. No tools. "
                  "Propose one minimal change as exact before and after source fragments, plus a reason. "
                  "The before fragment must occur exactly once. Preserve unrelated behavior and license notices. "
                  "Do not claim tests were run. If no safe change is justified, return before and after empty.")
        schema = {"type": "object", "additionalProperties": False,
                  "properties": {k: {"type": "string"} for k in ("reason", "before", "after")},
                  "required": ["reason", "before", "after"]}
        def operation():
            raw = SERVICE.answer([{"role": "user", "content": f"FILE: {relative}\nISSUE: {issue}\nSOURCE:\n{source}"}],
                                 self.settings, prompt, active=self._alive.is_set,
                                 response_schema=schema, context_limit=300000)
            obj = json.loads(raw)
            return self.agent.propose_change(relative, obj["before"], obj["after"], obj["reason"], original_hash)
        def apply(proposal):
            self.proposal = proposal
            self.show(proposal.reason + "\n\n" + proposal.diff)
            self.approve_button.config(state="normal")
        self._run(operation, apply)

    def approve(self):
        if self.proposal is None or self._busy:
            return
        proposal = self.proposal
        self.reject()
        self._run(lambda: self.agent.approve(proposal, approved=True),
                  lambda result: self.show(f"Approved edit applied. Test exit: {result[0]}\n{result[1]}"))
