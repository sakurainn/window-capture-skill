# -*- coding: utf-8 -*-
"""screen_fetch 各平台后端共享的数据结构与进程工具。"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile


class ScreenFetchError(RuntimeError):
    """可预期的失败（参数错误、找不到窗口、截图失败等）。"""


class WindowInfo:
    __slots__ = ("hwnd", "pid", "cls", "title", "exe", "rect", "visible", "minimized")

    def __init__(self, hwnd, pid, cls, title, exe, rect, visible, minimized):
        self.hwnd = hwnd  # int 或平台字符串（Sway con_id / Hyprland address）
        self.pid = pid
        self.cls = cls
        self.title = title
        self.exe = exe
        self.rect = rect  # (l, t, r, b)
        self.visible = visible
        self.minimized = minimized

    @property
    def size(self):
        return (self.rect[2] - self.rect[0], self.rect[3] - self.rect[1])

    def as_dict(self):
        if isinstance(self.hwnd, int):
            hex_id = "0x%X" % self.hwnd
        else:
            hex_id = str(self.hwnd)
        return {
            "hwnd": self.hwnd,
            "hex": hex_id,
            "pid": self.pid,
            "class": self.cls,
            "title": self.title,
            "exe": self.exe,
            "rect": list(self.rect),
            "size": list(self.size),
            "visible": self.visible,
            "minimized": self.minimized,
        }


class Frame:
    """一次截图结果：BGRA 原始像素，或已由系统工具写好的图片文件。"""

    __slots__ = ("width", "height", "bgra", "path", "method", "tempdir")

    def __init__(self, width, height, bgra=None, path=None, method="screen", tempdir=None):
        self.width = width
        self.height = height
        self.bgra = bgra
        self.path = path
        self.method = method
        self.tempdir = tempdir

    def cleanup(self):
        if self.tempdir:
            shutil.rmtree(self.tempdir, ignore_errors=True)
            self.tempdir = None


def warn(message):
    print("警告：%s" % message, file=sys.stderr, flush=True)


def which(*names):
    for name in names:
        path = shutil.which(name)
        if path:
            return path
    return None


def run_text(cmd, timeout=30):
    """执行命令并返回 CompletedProcess（文本模式）。不自动判定退出码。"""
    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except FileNotFoundError:
        raise ScreenFetchError("找不到命令：%s" % cmd[0])
    except subprocess.TimeoutExpired:
        raise ScreenFetchError("命令超时：%s" % " ".join(map(str, cmd)))
    except OSError as exc:
        raise ScreenFetchError("执行 %s 失败：%s" % (cmd[0], exc))


def check_text(cmd, timeout=30):
    proc = run_text(cmd, timeout)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise ScreenFetchError("%s 失败（%d）：%s" % (cmd[0], proc.returncode, detail))
    return proc.stdout


def make_temp_png():
    directory = tempfile.mkdtemp(prefix="screen_fetch_")
    return directory, os.path.join(directory, "shot.png")


def png_size(path):
    """不依赖 Pillow，从 PNG 的 IHDR 读取像素尺寸。"""
    try:
        with open(path, "rb") as fh:
            head = fh.read(24)
    except OSError:
        return None
    if len(head) >= 24 and head[:8] == b"\x89PNG\r\n\x1a\n" and head[12:16] == b"IHDR":
        return int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")
    return None


def image_size(path, fallback=(0, 0)):
    return png_size(path) or fallback


def linux_exe(pid, cache=None):
    """Linux 下读取 /proc/<pid>/exe 的 basename。"""
    if not pid:
        return ""
    if cache is not None and pid in cache:
        return cache[pid]
    name = ""
    try:
        name = os.path.basename(os.readlink("/proc/%d/exe" % int(pid)))
    except (OSError, ValueError):
        name = ""
    if cache is not None:
        cache[pid] = name
    return name
