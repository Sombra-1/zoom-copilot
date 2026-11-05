"""Internal isolated Windows PrintWindow helper; no desktop fallback."""
import ctypes
import sys


def print_window(handle, output):
    from ctypes import wintypes as w
    from PIL import Image
    user = ctypes.WinDLL("user32", use_last_error=True)
    gdi = ctypes.WinDLL("gdi32", use_last_error=True)
    user.IsWindow.argtypes = [w.HWND]
    user.IsIconic.argtypes = [w.HWND]
    user.GetWindowRect.argtypes = [w.HWND, ctypes.POINTER(w.RECT)]
    user.GetWindowDC.argtypes, user.GetWindowDC.restype = [w.HWND], w.HDC
    user.ReleaseDC.argtypes = [w.HWND, w.HDC]
    user.PrintWindow.argtypes, user.PrintWindow.restype = [w.HWND, w.HDC, w.UINT], w.BOOL
    gdi.CreateCompatibleDC.argtypes, gdi.CreateCompatibleDC.restype = [w.HDC], w.HDC
    gdi.CreateCompatibleBitmap.argtypes = [w.HDC, ctypes.c_int, ctypes.c_int]
    gdi.CreateCompatibleBitmap.restype = w.HBITMAP
    gdi.SelectObject.argtypes, gdi.SelectObject.restype = [w.HDC, w.HANDLE], w.HANDLE
    gdi.DeleteObject.argtypes = [w.HANDLE]
    gdi.DeleteDC.argtypes = [w.HDC]
    class Header(ctypes.Structure):
        _fields_ = [("size", w.DWORD), ("width", w.LONG), ("height", w.LONG),
                    ("planes", w.WORD), ("bits", w.WORD), ("compression", w.DWORD),
                    ("image_size", w.DWORD), ("x", w.LONG), ("y", w.LONG),
                    ("colors", w.DWORD), ("important", w.DWORD)]
    gdi.GetDIBits.argtypes = [w.HDC, w.HBITMAP, w.UINT, w.UINT, ctypes.c_void_p,
                            ctypes.POINTER(Header), w.UINT]
    rect = w.RECT()
    if not user.IsWindow(handle) or user.IsIconic(handle) or not user.GetWindowRect(handle, ctypes.byref(rect)):
        raise RuntimeError("Window unavailable")
    width, height = rect.right - rect.left, rect.bottom - rect.top
    if width < 1 or height < 1 or width * height > 32_000_000:
        raise RuntimeError("Invalid window size")
    dc = user.GetWindowDC(handle)
    memory = gdi.CreateCompatibleDC(dc)
    bitmap = gdi.CreateCompatibleBitmap(dc, width, height)
    old = gdi.SelectObject(memory, bitmap)
    try:
        if not user.PrintWindow(handle, memory, 2):
            raise RuntimeError("PrintWindow failed")
        gdi.SelectObject(memory, old)
        old = None
        header = Header(ctypes.sizeof(Header), width, -height, 1, 32, 0, 0, 0, 0, 0, 0)
        buffer = ctypes.create_string_buffer(width * height * 4)
        if not gdi.GetDIBits(memory, bitmap, 0, height, buffer, ctypes.byref(header), 0):
            raise RuntimeError("GetDIBits failed")
        Image.frombytes("RGB", (width, height), buffer.raw, "raw", "BGRX").save(output)
    finally:
        if old:
            gdi.SelectObject(memory, old)
        gdi.DeleteObject(bitmap)
        gdi.DeleteDC(memory)
        user.ReleaseDC(handle, dc)


if __name__ == "__main__":
    try:
        # Match the parent app's physical screen coordinate convention.
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        print_window(int(sys.argv[1]), sys.argv[2])
    except Exception:
        sys.exit(1)
