# -*- coding: utf-8 -*-
"""Windows 后端：纯 ctypes 调用 Win32 API（user32 / gdi32 / dwmapi / kernel32）。"""

from __future__ import annotations

import ctypes
import os
import time
from ctypes import wintypes

from sf_common import Frame, ScreenFetchError, WindowInfo

PW_CLIENTONLY = 0x00000001
PW_RENDERFULLCONTENT = 0x00000002
SRCCOPY = 0x00CC0020
BI_RGB = 0
DIB_RGB_COLORS = 0
DWMWA_EXTENDED_FRAME_BOUNDS = 9
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
SW_RESTORE = 9

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
try:
    dwmapi = ctypes.WinDLL("dwmapi")
except OSError:  # 极老系统 / 精简系统
    dwmapi = None


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


class MONITORINFOEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
        ("szDevice", wintypes.WCHAR * 32),
    ]


WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
MONITORENUMPROC = ctypes.WINFUNCTYPE(
    wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.LPARAM
)

user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
user32.EnumWindows.restype = wintypes.BOOL
user32.IsWindow.argtypes = [wintypes.HWND]
user32.IsWindow.restype = wintypes.BOOL
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL
user32.IsIconic.argtypes = [wintypes.HWND]
user32.IsIconic.restype = wintypes.BOOL
user32.IsZoomed.argtypes = [wintypes.HWND]
user32.IsZoomed.restype = wintypes.BOOL
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextLengthW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetClassNameW.restype = ctypes.c_int
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetWindowRect.restype = wintypes.BOOL
user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetClientRect.restype = wintypes.BOOL
user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
user32.ClientToScreen.restype = wintypes.BOOL
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.GetDC.argtypes = [wintypes.HWND]
user32.GetDC.restype = wintypes.HDC
user32.GetWindowDC.argtypes = [wintypes.HWND]
user32.GetWindowDC.restype = wintypes.HDC
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
user32.ReleaseDC.restype = ctypes.c_int
user32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
user32.PrintWindow.restype = wintypes.BOOL
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.ShowWindow.restype = wintypes.BOOL
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.SetForegroundWindow.restype = wintypes.BOOL
user32.GetForegroundWindow.argtypes = []
user32.GetForegroundWindow.restype = wintypes.HWND
user32.BringWindowToTop.argtypes = [wintypes.HWND]
user32.BringWindowToTop.restype = wintypes.BOOL
user32.SetProcessDPIAware.restype = wintypes.BOOL
user32.EnumDisplayMonitors.argtypes = [
    wintypes.HDC,
    ctypes.POINTER(wintypes.RECT),
    MONITORENUMPROC,
    wintypes.LPARAM,
]
user32.EnumDisplayMonitors.restype = wintypes.BOOL
user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFOEXW)]
user32.GetMonitorInfoW.restype = wintypes.BOOL

gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.DeleteObject.restype = wintypes.BOOL
gdi32.DeleteDC.argtypes = [wintypes.HDC]
gdi32.DeleteDC.restype = wintypes.BOOL
gdi32.BitBlt.argtypes = [
    wintypes.HDC,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.HDC,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.DWORD,
]
gdi32.BitBlt.restype = wintypes.BOOL
gdi32.GetDIBits.argtypes = [
    wintypes.HDC,
    wintypes.HBITMAP,
    wintypes.UINT,
    wintypes.UINT,
    ctypes.c_void_p,
    ctypes.POINTER(BITMAPINFO),
    wintypes.UINT,
]
gdi32.GetDIBits.restype = ctypes.c_int

kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.LPWSTR,
    ctypes.POINTER(wintypes.DWORD),
]
kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL

if dwmapi is not None:
    dwmapi.DwmGetWindowAttribute.argtypes = [
        wintypes.HWND,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    dwmapi.DwmGetWindowAttribute.restype = ctypes.c_long


def enable_dpi_awareness():
    """让坐标/截图按物理像素工作（必须在任何窗口查询之前调用）。"""
    try:  # Win10 1703+
        ctx = ctypes.c_void_p(-4)  # PER_MONITOR_AWARE_V2
        if user32.SetProcessDpiAwarenessContext(ctx):
            return
    except AttributeError:
        pass
    except OSError:
        pass
    try:  # Win8.1+
        ctypes.WinDLL("shcore").SetProcessDpiAwareness(2)
        return
    except Exception:
        pass
    try:  # Vista+
        user32.SetProcessDPIAware()
    except Exception:
        pass


def _window_title(hwnd):
    n = user32.GetWindowTextLengthW(hwnd)
    if n <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def _window_class(hwnd):
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def _process_path(pid):
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(1024)
        buf = ctypes.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return buf.value
        return ""
    finally:
        kernel32.CloseHandle(handle)


def _raw_window_rect(hwnd):
    """优先取 DWM 扩展边框（去掉 Win10 不可见的缩放边框），失败退回 GetWindowRect。"""
    rect = wintypes.RECT()
    if dwmapi is not None:
        hr = dwmapi.DwmGetWindowAttribute(
            hwnd,
            DWMWA_EXTENDED_FRAME_BOUNDS,
            ctypes.byref(rect),
            ctypes.sizeof(rect),
        )
        if hr == 0 and (rect.right > rect.left) and (rect.bottom > rect.top):
            return rect
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        raise ScreenFetchError("GetWindowRect 失败：%s" % ctypes.WinError(ctypes.get_last_error()))
    return rect


def _window_info(hwnd):
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    rect = _raw_window_rect(hwnd)
    return WindowInfo(
        hwnd=hwnd,
        pid=pid.value,
        cls=_window_class(hwnd),
        title=_window_title(hwnd),
        exe=os.path.basename(_process_path(pid.value)),
        rect=(rect.left, rect.top, rect.right, rect.bottom),
        visible=bool(user32.IsWindowVisible(hwnd)),
        minimized=bool(user32.IsIconic(hwnd)),
    )


def _parse_hwnd(value):
    text = str(value).strip()
    try:
        return int(text, 16) if text.lower().startswith(("0x", "0X")) else int(text, 10)
    except ValueError:
        raise ScreenFetchError("--hwnd 不是合法数字：%s" % value)


def _dib_to_bgra(dc, bmp, width, height):
    """把 HBITMAP 读成自上而下的 BGRA 字节串。"""
    bmi = BITMAPINFO()
    bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth = width
    bmi.bmiHeader.biHeight = -height  # 负数 = top-down
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 32
    bmi.bmiHeader.biCompression = BI_RGB

    buf = ctypes.create_string_buffer(width * height * 4)
    lines = gdi32.GetDIBits(dc, bmp, 0, height, buf, ctypes.byref(bmi), DIB_RGB_COLORS)
    if lines != height:
        raise ScreenFetchError("GetDIBits 只拿到 %d/%d 行" % (lines, height))
    return buf.raw


def _grab(width, height, draw):
    """建 32bpp 兼容位图，交给 draw(dc) 绘制，再读回像素。"""
    if width <= 0 or height <= 0:
        raise ScreenFetchError("截图区域尺寸无效：%dx%d" % (width, height))

    screen_dc = user32.GetDC(None)
    if not screen_dc:
        raise ScreenFetchError("GetDC(NULL) 失败：%s" % ctypes.WinError(ctypes.get_last_error()))
    mem_dc = None
    bmp = None
    old = None
    try:
        mem_dc = gdi32.CreateCompatibleDC(screen_dc)
        if not mem_dc:
            raise ScreenFetchError("CreateCompatibleDC 失败")
        bmp = gdi32.CreateCompatibleBitmap(screen_dc, width, height)
        if not bmp:
            raise ScreenFetchError("CreateCompatibleBitmap 失败")
        old = gdi32.SelectObject(mem_dc, bmp)
        if not draw(mem_dc):
            raise ScreenFetchError("绘制到内存位图失败：%s" % ctypes.WinError(ctypes.get_last_error()))
        return _dib_to_bgra(mem_dc, bmp, width, height)
    finally:
        if mem_dc and old:
            gdi32.SelectObject(mem_dc, old)
        if bmp:
            gdi32.DeleteObject(bmp)
        if mem_dc:
            gdi32.DeleteDC(mem_dc)
        user32.ReleaseDC(None, screen_dc)


def _looks_blank(data, width, height):
    """采样判断是否“整片纯黑/纯色”，用于 auto 模式回退。"""
    if not data:
        return True
    total = len(data)
    step = max(4, (total // 4096) // 4 * 4)
    lo, hi = 255, 0
    for i in range(0, total, step):
        v = data[i]
        if v < lo:
            lo = v
        if v > hi:
            hi = v
        if hi - lo > 24:
            return False
    return hi <= 24  # 纯黑 / 近黑视为失败


def _draw_print(hwnd, client, flags):
    extra = flags | (PW_CLIENTONLY if client else 0)

    def _draw(dc):
        return bool(user32.PrintWindow(hwnd, dc, extra))

    return _draw


def _draw_window_dc(hwnd, client, width, height):
    def _draw(dc):
        src = user32.GetDC(hwnd) if client else user32.GetWindowDC(hwnd)
        if not src:
            return False
        try:
            return bool(gdi32.BitBlt(dc, 0, 0, width, height, src, 0, 0, SRCCOPY))
        finally:
            user32.ReleaseDC(hwnd, src)

    return _draw


def _draw_screen(x, y, width, height):
    def _draw(dc):
        src = user32.GetDC(None)
        if not src:
            return False
        try:
            return bool(gdi32.BitBlt(dc, 0, 0, width, height, src, x, y, SRCCOPY))
        finally:
            user32.ReleaseDC(None, src)

    return _draw


def _window_rect(hwnd, client=False):
    """返回要截取的窗口屏幕矩形 (x, y, w, h)。"""
    if user32.IsIconic(hwnd):
        raise ScreenFetchError("窗口已最小化，无法按窗口矩形截图（可加 --activate 先还原）")

    if client:
        rect = wintypes.RECT()
        if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
            raise ScreenFetchError("GetClientRect 失败")
        origin = wintypes.POINT(0, 0)
        if not user32.ClientToScreen(hwnd, ctypes.byref(origin)):
            raise ScreenFetchError("ClientToScreen 失败")
        x, y = origin.x, origin.y
        w, h = rect.right - rect.left, rect.bottom - rect.top
    else:
        r = _raw_window_rect(hwnd)
        x, y, w, h = r.left, r.top, r.right - r.left, r.bottom - r.top

    if w <= 0 or h <= 0:
        raise ScreenFetchError("窗口尺寸为 0（可能未显示）：%dx%d" % (w, h))
    return x, y, w, h


class WindowsBackend:
    name = "windows"

    def __init__(self):
        enable_dpi_awareness()

    def list_windows(self, include_hidden=True):
        collected = []

        @WNDENUMPROC
        def _cb(hwnd, _lparam):
            if user32.IsWindow(hwnd):
                collected.append(_window_info(hwnd))
            return True

        user32.EnumWindows(_cb, 0)
        return collected

    def window_by_id(self, value):
        hwnd = _parse_hwnd(value)
        if not user32.IsWindow(hwnd):
            raise ScreenFetchError("HWND %s 不存在或已关闭" % value)
        return _window_info(hwnd)

    def list_monitors(self):
        monitors = []

        @MONITORENUMPROC
        def _cb(hmon, _hdc, _rect, _lparam):
            info = MONITORINFOEXW()
            info.cbSize = ctypes.sizeof(MONITORINFOEXW)
            if user32.GetMonitorInfoW(hmon, ctypes.byref(info)):
                r = info.rcMonitor
                monitors.append(
                    {
                        "index": len(monitors),
                        "handle": int(hmon) if hmon else 0,
                        "device": info.szDevice,
                        "rect": (r.left, r.top, r.right, r.bottom),
                        "work": (
                            info.rcWork.left,
                            info.rcWork.top,
                            info.rcWork.right,
                            info.rcWork.bottom,
                        ),
                        "primary": bool(info.dwFlags & 1),
                    }
                )
            return True

        user32.EnumDisplayMonitors(None, None, _cb, 0)
        return monitors

    def activate(self, win):
        hwnd = win.hwnd
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)
            time.sleep(0.15)
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        time.sleep(0.1)

    def is_foreground(self, win):
        return user32.GetForegroundWindow() == win.hwnd

    def capture_rect(self, x, y, w, h):
        data, width, height, _used = _capture_rect(x, y, w, h)
        return Frame(width, height, bgra=data, method="screen")

    def capture_monitor(self, index):
        mons = self.list_monitors()
        if not (0 <= index < len(mons)):
            raise ScreenFetchError("--monitor 越界：共 %d 个显示器" % len(mons))
        x1, y1, x2, y2 = mons[index]["rect"]
        return self.capture_rect(x1, y1, x2 - x1, y2 - y1)

    def capture_window(self, win, method="auto", client=False, flags=PW_RENDERFULLCONTENT):
        data, width, height, used = _capture_window(
            win.hwnd, method=method, client=client, flags=flags
        )
        return Frame(width, height, bgra=data, method=used)


def _capture_window(hwnd, *, method="auto", client=False, flags=PW_RENDERFULLCONTENT):
    x, y, w, h = _window_rect(hwnd, client=client)
    method = method.lower()

    def _print():
        return _grab(w, h, _draw_print(hwnd, client, flags)), w, h

    def _screen():
        return _grab(w, h, _draw_screen(x, y, w, h)), w, h

    def _bitblt():
        return _grab(w, h, _draw_window_dc(hwnd, client, w, h)), w, h

    if method == "print":
        return (*_print(), "print")
    if method == "bitblt":
        return (*_bitblt(), "bitblt")
    if method == "screen":
        return (*_screen(), "screen")
    if method != "auto":
        raise ScreenFetchError("未知的 --method：%s" % method)

    # auto：PrintWindow 优先；全黑则用屏幕抓取兜底
    data, w, h = _print()
    if not _looks_blank(data, w, h) or not user32.IsWindowVisible(hwnd):
        return data, w, h, "print"
    data, w, h = _screen()
    return data, w, h, "screen"


def _capture_rect(x, y, w, h):
    return _grab(w, h, _draw_screen(x, y, w, h)), w, h, "screen"
