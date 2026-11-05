"""Queue worker callbacks without calling Tcl from worker threads."""
import queue
import threading
import tkinter as tk


class UiDispatcher:
    def __init__(self, root):
        self.root = root
        self.thread = threading.get_ident()
        self.queue = queue.Queue(maxsize=2048)
        self.closed = False
        self._timer = root.after(20, self._drain)

    def post(self, function):
        if self.closed:
            return False
        if threading.get_ident() == self.thread:
            function()
            return True
        try:
            self.queue.put_nowait(function)
            return True
        except queue.Full:
            return False

    def _drain(self):
        if self.closed:
            return
        # Also safe when explicitly drained by a construction/test harness.
        self.root.after_cancel(self._timer)
        for _ in range(100):
            if self.closed:
                return
            try:
                function = self.queue.get_nowait()
            except queue.Empty:
                break
            try:
                function()
            except Exception as exc:
                self.root.report_callback_exception(type(exc), exc, exc.__traceback__)
        if not self.closed:
            self._timer = self.root.after(20, self._drain)

    def close(self):
        if self.closed:
            return
        self.closed = True
        try:
            self.root.after_cancel(self._timer)
        except tk.TclError:
            pass
        while True:
            try:
                self.queue.get_nowait()
            except queue.Empty:
                break
