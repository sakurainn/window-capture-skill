# -*- coding: utf-8 -*-
"""macOS 后端：screencapture + osascript + system_profiler（均为系统自带）。"""

from __future__ import annotations

import json
import os
import re
import time

from sf_common import (
    Frame,
    ScreenFetchError,
    WindowInfo,
    check_text,
    image_size,
    make_temp_png,
    run_text,
    warn,
    which,
)

_WINDOW_SCRIPT = r'''
tell application "System Events"
	set output to ""
	repeat with proc in (every application process whose background only is false)
		try
			set pname to name of proc
			set ppid to unix id of proc
			repeat with w in windows of proc
				try
					set wname to name of w
					set {wx, wy} to position of w
					set {ww, wh} to size of w
					set wmin to "0"
					try
						if value of attribute "AXMinimized" of w then set wmin to "1"
					end try
					set output to output & ppid & tab & pname & tab & wname & tab & wx & tab & wy & tab & ww & tab & wh & tab & wmin & linefeed
				end try
			end repeat
		end try
	end repeat
	return output
end tell
'''


def _ps_exe(pid, cache):
    if not pid:
        return ""
    if pid in cache:
        return cache[pid]
    proc = run_text(["ps", "-p", str(pid), "-o", "comm="], timeout=5)
    name = proc.stdout.strip() if proc.returncode == 0 else ""
    cache[pid] = name
    return name


def _applescript_quote(text):
    return str(text).replace("\\", "\\\\").replace('"', '\\"')


class DarwinBackend:
    name = "macos"

    def __init__(self):
        if not which("screencapture"):
            raise ScreenFetchError("找不到 screencapture，无法在 macOS 上截图")
        self._exe_cache = {}

    def _osa(self, script, timeout=30):
        return check_text(["osascript", "-e", script], timeout=timeout)

    def _try_osa(self, script, timeout=10):
        proc = run_text(["osascript", "-e", script], timeout=timeout)
        return proc.returncode == 0

    def list_windows(self, include_hidden=True):
        try:
            out = self._osa(_WINDOW_SCRIPT, timeout=40)
        except ScreenFetchError as exc:
            raise ScreenFetchError(
                "%s；请到 系统设置 > 隐私与安全性 > 辅助功能 给终端/IDE 授权" % exc
            )
        wins = []
        for line in out.splitlines():
            parts = line.split("\t")
            if len(parts) < 8:
                continue
            pid_s, pname, title, x_s, y_s, w_s, h_s, min_s = parts[:8]
            try:
                pid = int(pid_s)
                x, y = int(float(x_s)), int(float(y_s))
                w, h = int(float(w_s)), int(float(h_s))
            except ValueError:
                continue
            minimized = min_s.strip() == "1"
            wins.append(
                WindowInfo(
                    hwnd="pid:%d:%d" % (pid, len(wins)),
                    pid=pid,
                    cls=pname,
                    title=title,
                    exe=os.path.basename(_ps_exe(pid, self._exe_cache)),
                    rect=(x, y, x + w, y + h),
                    visible=True,
                    minimized=minimized,
                )
            )
        return wins

    def window_by_id(self, value):
        text = str(value).strip().lower()
        for win in self.list_windows(include_hidden=True):
            if str(win.hwnd).lower() == text:
                return win
        raise ScreenFetchError("找不到窗口 ID：%s（可用 --list 查看）" % value)

    def list_monitors(self):
        monitors = []
        try:
            data = json.loads(check_text(["system_profiler", "SPDisplaysDataType", "-json"], 25))
        except Exception:
            data = {}
        for gpu in data.get("SPDisplaysDataType", []) or []:
            for display in gpu.get("spdisplays_ndrvs", []) or []:
                text = " ".join(
                    str(display.get(key, ""))
                    for key in ("_spdisplays_resolution", "_spdisplays_pixels")
                )
                match = re.search(r"(\d+)\s*[x×]\s*(\d+)", text)
                w, h = (int(match.group(1)), int(match.group(2))) if match else (0, 0)
                primary = str(display.get("spdisplays_main", "")).lower() in (
                    "yes",
                    "spdisplays_yes",
                    "true",
                )
                monitors.append(
                    {
                        "index": len(monitors),
                        "handle": 0,
                        "device": display.get("_name", "display"),
                        "rect": (0, 0, w, h),
                        "work": (0, 0, w, h),
                        "primary": primary,
                    }
                )
        if not monitors:
            monitors.append(
                {
                    "index": 0,
                    "handle": 0,
                    "device": "display",
                    "rect": (0, 0, 0, 0),
                    "work": (0, 0, 0, 0),
                    "primary": True,
                }
            )
        if not any(m["primary"] for m in monitors):
            monitors[0]["primary"] = True
        return monitors

    def activate(self, win):
        pid = win.pid
        self._try_osa(
            'tell application "System Events" to set frontmost of '
            "(first application process whose unix id is %d) to true" % pid,
            timeout=10,
        )
        if win.title:
            self._try_osa(
                'tell application "System Events" to tell '
                "(first application process whose unix id is %d) to try\n"
                'set value of attribute "AXMinimized" of (first window whose name is "%s") to false\n'
                "end try" % (pid, _applescript_quote(win.title)),
                timeout=10,
            )
        time.sleep(0.15)

    def _screencapture(self, extra_args, fallback_size):
        directory, path = make_temp_png()
        cmd = ["screencapture", "-x", "-o", "-t", "png"] + list(extra_args) + [path]
        proc = run_text(cmd, timeout=30)
        if proc.returncode != 0 or not os.path.exists(path) or os.path.getsize(path) == 0:
            Frame(0, 0, path=None, tempdir=directory).cleanup()
            detail = (proc.stderr or proc.stdout or "").strip()
            raise ScreenFetchError(
                "screencapture 失败%s；请到 系统设置 > 隐私与安全性 > 屏幕录制 授权终端/IDE"
                % (("：" + detail) if detail else "")
            )
        width, height = image_size(path, fallback_size)
        return Frame(width, height, path=path, method="screen", tempdir=directory)

    def capture_rect(self, x, y, w, h):
        return self._screencapture(["-R", "%d,%d,%d,%d" % (x, y, w, h)], (w, h))

    def capture_monitor(self, index):
        mons = self.list_monitors()
        if not (0 <= index < len(mons)):
            raise ScreenFetchError("--monitor 越界：共 %d 个显示器" % len(mons))
        x1, y1, x2, y2 = mons[index]["rect"]
        return self._screencapture(["-D", str(index + 1)], (x2 - x1, y2 - y1))

    def capture_window(self, win, method="auto", client=False, flags=0):
        if method not in ("auto", "screen"):
            warn("--method %s 仅 Windows 支持，已改用屏幕截图" % method)
        if client:
            warn("macOS 后端无法区分客户区，已按整窗截图")
        if win.minimized:
            warn("窗口已最小化，建议加 --activate 先还原")
        x1, y1, x2, y2 = win.rect
        return self._screencapture(
            ["-R", "%d,%d,%d,%d" % (x1, y1, x2 - x1, y2 - y1)],
            (x2 - x1, y2 - y1),
        )
