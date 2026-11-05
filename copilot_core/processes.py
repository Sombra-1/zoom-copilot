"""Own subprocess trees, keep Windows helpers invisible, reap on every exit path."""
import os
import signal
import subprocess
import threading


def quiet_process_options():
    """Keep Windows console helpers off the taskbar, including under pythonw."""
    return {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}


class OwnedProcess:
    def __init__(self, command, **kwargs):
        self.job = None
        self._close_lock = threading.Lock()
        self._closed = False
        if os.name == "nt":
            kwargs["creationflags"] = kwargs.get("creationflags", 0) | subprocess.CREATE_NO_WINDOW
        else:
            kwargs["start_new_session"] = True
        self.process = subprocess.Popen(command, **kwargs)  # shell is never enabled
        if os.name == "nt":
            try:
                self._assign_job()
            except Exception:
                self.process.kill()
                self.process.wait()
                raise RuntimeError("Could not establish Codex process cleanup boundary") from None

    def _assign_job(self):
        import ctypes
        from ctypes import wintypes as w

        class Basic(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64),
                        ("PerJobUserTimeLimit", ctypes.c_int64), ("LimitFlags", w.DWORD),
                        ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t),
                        ("ActiveProcessLimit", w.DWORD), ("Affinity", ctypes.c_size_t),
                        ("PriorityClass", w.DWORD), ("SchedulingClass", w.DWORD)]

        class IO(ctypes.Structure):
            _fields_ = [(name, ctypes.c_uint64) for name in
                        ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                         "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

        class Limits(ctypes.Structure):
            _fields_ = [("BasicLimitInformation", Basic), ("IoInfo", IO),
                        ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                        ("PeakProcessMemoryUsed", ctypes.c_size_t),
                        ("PeakJobMemoryUsed", ctypes.c_size_t)]

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, w.LPCWSTR]
        kernel.CreateJobObjectW.restype = w.HANDLE
        kernel.SetInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD]
        kernel.SetInformationJobObject.restype = w.BOOL
        kernel.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
        kernel.AssignProcessToJobObject.restype = w.BOOL
        kernel.CloseHandle.argtypes = [w.HANDLE]
        kernel.CloseHandle.restype = w.BOOL
        job = kernel.CreateJobObjectW(None, None)
        limits = Limits()
        limits.BasicLimitInformation.LimitFlags = 0x2000  # KILL_ON_JOB_CLOSE
        if not job:
            raise OSError("CreateJobObject failed")
        if not kernel.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            kernel.CloseHandle(job)
            raise OSError("SetInformationJobObject failed")
        if not kernel.AssignProcessToJobObject(job, w.HANDLE(int(self.process._handle))):
            kernel.CloseHandle(job)
            raise OSError("AssignProcessToJobObject failed")
        self.job, self._kernel = job, kernel

    def close(self):
        with self._close_lock:
            if self._closed:
                return
            self._closed = True
            self._close()

    def _close(self):
        proc = self.process
        if self.job:
            self._kernel.CloseHandle(self.job)
            self.job = None
        elif os.name != "nt":
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        elif proc.poll() is None:
            proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            if os.name != "nt":
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            else:
                proc.kill()
            proc.wait(timeout=2)
        if os.name != "nt":
            # A parent may exit before a child that ignored SIGTERM.
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        for pipe in (proc.stdin, proc.stdout, proc.stderr):
            if pipe:
                pipe.close()
