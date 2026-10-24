# -*- coding: utf-8 -*-
"""Linux 后端：X11 用 wmctrl/xdotool + maim/ImageMagick/scrot；Wayland 用 grim 等。"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time

from sf_common import (
    Frame,
    ScreenFetchError,
    WindowInfo,
    check_text,
    image_size,
    linux_exe,
    make_temp_png,
    run_text,
    warn,
    which,
)

_DESKTOP_ICON = None


def _norm_id(value):
    text = str(value).strip().lower()
    try:
        return int(text, 16) if text.startswith(("0x", "0X")) else int(text, 10)
    except ValueError:
        return text


class LinuxBackend:
    name = "linux"

    def __init__(self):
        self.wayland = bool(os.environ.get("WAYLAND_DISPLAY")) or (
            os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"
        )
        self._exe_cache = {}
        self._tool = None

    # ------------------------------------------------------------------ #
    # 窗口枚举
    # ------------------------------------------------------------------ #

    def list_windows(self, include_hidden=True):
        if self.wayland:
            wins = self._sway_windows(include_hidden)
            if wins is not None:
                return wins
            wins = self._hypr_windows(include_hidden)
            if wins is not None:
                return wins
        wins = self._x11_windows(include_hidden)
        if wins is None:
            raise ScreenFetchError(
                "无法枚举窗口：X11 需要 wmctrl 或 xdotool；"
                "Wayland 需要 swaymsg / hyprctl（GNOME/KDE Wayland 暂不支持窗口枚举）"
            )
        return wins

    def window_by_id(self, value):
        target = _norm_id(value)
        for win in self.list_windows(include_hidden=True):
            if _norm_id(win.hwnd) == target:
                return win
        raise ScreenFetchError("找不到窗口 ID：%s（可用 --list 查看）" % value)

    def _x11_windows(self, include_hidden):
        wmctrl = which("wmctrl")
        if wmctrl:
            try:
                out = check_text([wmctrl, "-lpGx"], timeout=15)
            except ScreenFetchError:
                out = ""
            wins = []
            for line in out.splitlines():
                parts = line.split(None, 9)
                if len(parts) < 10:
                    continue
                wid_s, _desktop, pid_s, x_s, y_s, w_s, h_s, _host, cls, title = parts
                try:
                    wid = int(wid_s, 16)
                    pid = int(pid_s)
                    x, y = int(x_s), int(y_s)
                    w, h = int(w_s), int(h_s)
                except ValueError:
                    continue
                if not include_hidden and not title.strip():
                    continue
                wins.append(
                    WindowInfo(
                        hwnd=wid,
                        pid=pid,
                        cls=cls,
                        title=title,
                        exe=linux_exe(pid, self._exe_cache),
                        rect=(x, y, x + w, y + h),
                        visible=True,
                        minimized=False,
                    )
                )
            return wins

        xdotool = which("xdotool")
        if xdotool:
            flags = ["search", "--name", ".*"]
            if not include_hidden:
                flags.insert(1, "--onlyvisible")
            try:
                ids = check_text([xdotool] + flags, timeout=15).split()
            except ScreenFetchError:
                return []
            wins = []
            for wid_s in ids:
                try:
                    wid = int(wid_s)
                except ValueError:
                    continue
                title = run_text([xdotool, "getwindowname", str(wid)], timeout=5)
                pid_s = run_text([xdotool, "getwindowpid", str(wid)], timeout=5)
                geom = run_text([xdotool, "getwindowgeometry", "--shell", str(wid)], timeout=5)
                title_text = title.stdout.strip() if title.returncode == 0 else ""
                if not include_hidden and not title_text:
                    continue
                try:
                    pid = int(pid_s.stdout.strip())
                except (ValueError, AttributeError):
                    pid = 0
                values = {}
                for logline in geom.stdout.splitlines():
                    if "=" in logline:
                        key, val = logline.split("=", 1)
                        values[key.strip()] = val.strip()
                try:
                    x, y = int(values.get("X", 0)), int(values.get("Y", 0))
                    w, h = int(values.get("WIDTH", 0)), int(values.get("HEIGHT", 0))
                except ValueError:
                    continue
                wins.append(
                    WindowInfo(
                        hwnd=wid,
                        pid=pid,
                        cls="",
                        title=title_text,
                        exe=linux_exe(pid, self._exe_cache),
                        rect=(x, y, x + w, y + h),
                        visible=True,
                        minimized=False,
                    )
                )
            return wins
        return None

    def _sway_windows(self, include_hidden):
        swaymsg = which("swaymsg")
        if not swaymsg:
            return None
        try:
            tree = json.loads(check_text([swaymsg, "-t", "get_tree"], timeout=15))
        except (ScreenFetchError, ValueError):
            return None
        wins = []

        def walk(node):
            if node.get("type") in ("con", "floating_con") and node.get("pid"):
                rect = node.get("rect") or {}
                x, y = int(rect.get("x", 0)), int(rect.get("y", 0))
                w, h = int(rect.get("width", 0)), int(rect.get("height", 0))
                name = node.get("name") or ""
                if include_hidden or name.strip():
                    pid = int(node.get("pid") or 0)
                    wins.append(
                        WindowInfo(
                            hwnd=int(node.get("id") or 0),
                            pid=pid,
                            cls=node.get("app_id") or node.get("shell") or "",
                            title=name,
                            exe=linux_exe(pid, self._exe_cache),
                            rect=(x, y, x + w, y + h),
                            visible=bool(node.get("visible", True)),
                            minimized=False,
                        )
                    )
            for key in ("nodes", "floating_nodes"):
                for child in node.get(key) or []:
                    walk(child)

        walk(tree)
        return wins

    def _hypr_windows(self, include_hidden):
        hyprctl = which("hyprctl")
        if not hyprctl:
            return None
        try:
            clients = json.loads(check_text([hyprctl, "clients", "-j"], timeout=15))
        except (ScreenFetchError, ValueError):
            return None
        wins = []
        for client in clients:
            title = client.get("title") or ""
            if not include_hidden and not title.strip():
                continue
            at = client.get("at") or [0, 0]
            size = client.get("size") or [0, 0]
            x, y = int(at[0]), int(at[1])
            w, h = int(size[0]), int(size[1])
            pid = int(client.get("pid") or 0)
            hidden = bool(client.get("hidden"))
            wins.append(
                WindowInfo(
                    hwnd=str(client.get("address") or ""),
                    pid=pid,
                    cls=client.get("class") or client.get("initialClass") or "",
                    title=title,
                    exe=linux_exe(pid, self._exe_cache),
                    rect=(x, y, x + w, y + h),
                    visible=bool(client.get("mapped")) and not hidden,
                    minimized=hidden,
                )
            )
        return wins

    # ------------------------------------------------------------------ #
    # 显示器
    # ------------------------------------------------------------------ #

    def list_monitors(self):
        if self.wayland:
            monitors = self._wayland_monitors()
            if monitors:
                return monitors
        return self._x11_monitors()

    def _x11_monitors(self):
        monitors = []
        xrandr = which("xrandr")
        if xrandr:
            try:
                out = check_text([xrandr, "--listmonitors"], timeout=10)
            except ScreenFetchError:
                out = ""
            for line in out.splitlines():
                match = re.match(
                    r"^\s*(\d+):\s+([+*]*)(\S+)\s+(\d+)/\d+x(\d+)/\d+\+(-?\d+)\+(-?\d+)",
                    line,
                )
                if not match:
                    continue
                index = int(match.group(1))
                flags = match.group(2)
                name = match.group(3)
                w, h = int(match.group(4)), int(match.group(5))
                x, y = int(match.group(6)), int(match.group(7))
                monitors.append(
                    {
                        "index": index,
                        "handle": 0,
                        "device": name,
                        "rect": (x, y, x + w, y + h),
                        "work": (x, y, x + w, y + h),
                        "primary": "*" in flags,
                    }
                )
        if monitors:
            return monitors

        w = h = 0
        try:
            info = check_text(["xdpyinfo"], timeout=10)
            match = re.search(r"dimensions:\s+(\d+)x(\d+)", info)
            if match:
                w, h = int(match.group(1)), int(match.group(2))
        except ScreenFetchError:
            pass
        return [
            {
                "index": 0,
                "handle": 0,
                "device": "display",
                "rect": (0, 0, w, h),
                "work": (0, 0, w, h),
                "primary": True,
            }
        ]

    def _wayland_monitors(self):
        monitors = []
        swaymsg = which("swaymsg")
        if swaymsg:
            try:
                outputs = json.loads(check_text([swaymsg, "-t", "get_outputs"], timeout=10))
            except (ScreenFetchError, ValueError):
                outputs = []
            for index, output in enumerate(outputs):
                rect = output.get("rect") or {}
                x, y = int(rect.get("x", 0)), int(rect.get("y", 0))
                w, h = int(rect.get("width", 0)), int(rect.get("height", 0))
                monitors.append(
                    {
                        "index": index,
                        "handle": 0,
                        "device": output.get("name", "output"),
                        "rect": (x, y, x + w, y + h),
                        "work": (x, y, x + w, y + h),
                        "primary": bool(output.get("focused")) and index == 0,
                    }
                )
            if monitors:
                monitors[0]["primary"] = True
                return monitors

        hyprctl = which("hyprctl")
        if hyprctl:
            try:
                outputs = json.loads(check_text([hyprctl, "monitors", "-j"], timeout=10))
            except (ScreenFetchError, ValueError):
                outputs = []
            for index, output in enumerate(outputs):
                x, y = int(output.get("x", 0)), int(output.get("y", 0))
                w, h = int(output.get("width", 0)), int(output.get("height", 0))
                monitors.append(
                    {
                        "index": index,
                        "handle": 0,
                        "device": output.get("name", "output"),
                        "rect": (x, y, x + w, y + h),
                        "work": (x, y, x + w, y + h),
                        "primary": index == 0,
                    }
                )
            if monitors:
                return monitors
        return []

    # ------------------------------------------------------------------ #
    # 激活
    # ------------------------------------------------------------------ #

    def activate(self, win):
        if self.wayland:
            swaymsg = which("swaymsg")
            if swaymsg:
                if run_text([swaymsg, "[con_id=%s] focus" % win.hwnd], timeout=5).returncode == 0:
                    time.sleep(0.1)
                    return
            hyprctl = which("hyprctl")
            if hyprctl:
                run_text(
                    [hyprctl, "dispatch", "focuswindow", "address:%s" % win.hwnd],
                    timeout=5,
                )
                time.sleep(0.1)
            return

        wmctrl = which("wmctrl")
        if wmctrl:
            proc = run_text([wmctrl, "-ia", "0x%x" % int(win.hwnd)], timeout=5)
            if proc.returncode == 0:
                time.sleep(0.1)
                return
        xdotool = which("xdotool")
        if xdotool:
            run_text([xdotool, "windowactivate", str(int(win.hwnd))], timeout=5)
            time.sleep(0.1)

    # ------------------------------------------------------------------ #
    # 截图
    # ------------------------------------------------------------------ #

    def _x11_tool(self):
        if self._tool is None:
            tool = (
                which("maim")
                or which("import")
                or which("scrot")
                or which("gnome-screenshot")
                or (which("xwd") if which("convert") else None)
            )
            if not tool:
                raise ScreenFetchError(
                    "未找到 X11 截图工具，请安装 maim / ImageMagick(import) / scrot / gnome-screenshot 之一"
                )
            self._tool = tool
        return self._tool

    def _x11_capture(self, x, y, w, h, window_id=None):
        tool_path = self._x11_tool()
        tool = os.path.basename(tool_path)
        directory, path = make_temp_png()
        try:
            if tool == "maim":
                cmd = [tool_path]
                if window_id is not None:
                    cmd += ["-i", "0x%x" % int(window_id)]
                elif x is not None:
                    cmd += ["-g", "%dx%d+%d+%d" % (w, h, x, y)]
                cmd.append(path)
                check_text(cmd, timeout=30)
            elif tool == "import":
                cmd = [tool_path, "-window", ("0x%x" % int(window_id)) if window_id is not None else "root"]
                if window_id is None and x is not None:
                    cmd += ["-crop", "%dx%d+%d+%d" % (w, h, x, y), "+repage"]
                cmd.append(path)
                check_text(cmd, timeout=30)
            elif tool == "scrot":
                if window_id is not None:
                    raise ScreenFetchError("scrot 不支持按窗口截图")
                cmd = [tool_path, "-o"]
                if x is not None:
                    cmd += ["-a", "%d,%d,%d,%d" % (x, y, w, h)]
                cmd.append(path)
                check_text(cmd, timeout=30)
            elif tool == "gnome-screenshot":
                if window_id is not None or x is not None:
                    raise ScreenFetchError("gnome-screenshot 仅支持全屏非交互截图")
                check_text([tool_path, "-f", path], timeout=30)
            else:  # xwd + convert
                src = [tool_path]
                if window_id is not None:
                    src += ["-id", "0x%x" % int(window_id)]
                else:
                    src += ["-root"]
                src += ["-silent"]
                proc = subprocess.run(src, capture_output=True)
                if proc.returncode != 0:
                    raise ScreenFetchError("xwd 截图失败：%s" % proc.stderr.decode("utf-8", "replace").strip())
                convert = which("convert")
                cmd = [convert, "xwd:-"]
                if window_id is None and x is not None:
                    cmd += ["-crop", "%dx%d+%d+%d" % (w, h, x, y), "+repage"]
                cmd.append(path)
                conv = subprocess.run(cmd, input=proc.stdout, capture_output=True)
                if conv.returncode != 0:
                    raise ScreenFetchError(
                        "ImageMagick convert 失败：%s" % conv.stderr.decode("utf-8", "replace").strip()
                    )

            if not os.path.exists(path) or os.path.getsize(path) == 0:
                raise ScreenFetchError("%s 没有生成截图文件" % tool)
            width, height = image_size(path, (w, h) if x is not None else (0, 0))
            return Frame(width, height, path=path, method="screen", tempdir=directory)
        except Exception:
            shutil.rmtree(directory, ignore_errors=True)
            raise

    def _x11_client_rect(self, window_id):
        xwininfo = which("xwininfo")
        if not xwininfo:
            return None
        proc = run_text([xwininfo, "-id", str(int(window_id))], timeout=5)
        if proc.returncode != 0:
            return None
        values = {}
        for line in proc.stdout.splitlines():
            match = re.match(r"^\s*(Absolute upper-left [XY]|Width|Height):\s+(-?\d+)", line)
            if match:
                values[match.group(1)] = int(match.group(2))
        try:
            return (
                values["Absolute upper-left X"],
                values["Absolute upper-left Y"],
                values["Width"],
                values["Height"],
            )
        except KeyError:
            return None

    def _wayland_capture(self, x, y, w, h):
        directory, path = make_temp_png()
        grim = which("grim")
        try:
            if grim:
                cmd = [grim]
                if x is not None:
                    cmd += ["-g", "%d,%d %dx%d" % (x, y, w, h)]
                cmd.append(path)
                check_text(cmd, timeout=30)
            elif x is None:
                spectacle = which("spectacle")
                gnome = which("gnome-screenshot")
                if spectacle:
                    check_text([spectacle, "-b", "-n", "-f", "-o", path], timeout=30)
                elif gnome:
                    check_text([gnome, "-f", path], timeout=30)
                else:
                    raise ScreenFetchError(
                        "Wayland 截图需要 grim；GNOME/KDE 可安装 grim 或使用 spectacle/gnome-screenshot"
                    )
            else:
                raise ScreenFetchError(
                    "当前 Wayland 会话不支持区域/窗口截图；请安装 grim 并使用 wlroots 系合成器（sway/Hyprland）"
                )

            if not os.path.exists(path) or os.path.getsize(path) == 0:
                raise ScreenFetchError("Wayland 截图工具没有生成文件")
            width, height = image_size(path, (w, h) if x is not None else (0, 0))
            return Frame(width, height, path=path, method="screen", tempdir=directory)
        except Exception:
            shutil.rmtree(directory, ignore_errors=True)
            raise

    def capture_rect(self, x, y, w, h):
        if w <= 0 or h <= 0:
            x = y = None
        if self.wayland:
            return self._wayland_capture(x, y, w, h)
        return self._x11_capture(x, y, w, h)

    def capture_monitor(self, index):
        monitors = self.list_monitors()
        if not (0 <= index < len(monitors)):
            raise ScreenFetchError("--monitor 越界：共 %d 个显示器" % len(monitors))
        monitor = monitors[index]
        x1, y1, x2, y2 = monitor["rect"]
        w, h = x2 - x1, y2 - y1

        if self.wayland:
            grim = which("grim")
            if grim and monitor["device"]:
                directory, path = make_temp_png()
                proc = run_text([grim, "-o", monitor["device"], path], timeout=30)
                if (
                    proc.returncode == 0
                    and os.path.exists(path)
                    and os.path.getsize(path) > 0
                ):
                    width, height = image_size(path, (w, h))
                    return Frame(width, height, path=path, method="screen", tempdir=directory)
                shutil.rmtree(directory, ignore_errors=True)
            if w > 0 and h > 0:
                return self._wayland_capture(x1, y1, w, h)
            return self._wayland_capture(None, None, None, None)

        if w > 0 and h > 0:
            return self._x11_capture(x1, y1, w, h)
        return self._x11_capture(None, None, None, None)

    def capture_window(self, win, method="auto", client=False, flags=0):
        if method not in ("auto", "screen"):
            warn("--method %s 仅 Windows 支持，已改用屏幕截图" % method)
        x1, y1, x2, y2 = win.rect
        x, y, w, h = x1, y1, x2 - x1, y2 - y1

        if self.wayland:
            if client:
                warn("Wayland 后端无法区分客户区，已按整窗截图")
            return self._wayland_capture(x, y, w, h)

        if client:
            rect = self._x11_client_rect(win.hwnd)
            if rect:
                return self._x11_capture(*rect)
            warn("xwininfo 不可用，--client 已退化为整窗截图")

        tool = os.path.basename(self._x11_tool())
        if tool in ("maim", "import", "xwd"):
            try:
                return self._x11_capture(0, 0, 0, 0, window_id=win.hwnd)
            except ScreenFetchError:
                pass
        return self._x11_capture(x, y, w, h)
