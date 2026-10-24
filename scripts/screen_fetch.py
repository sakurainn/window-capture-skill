#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""screen_fetch.py - 跨平台窗口/屏幕截图工具（Windows / macOS / Linux）。

依赖：
    - Python 3.8+
    - Windows：标准库 ctypes（user32 / gdi32 / dwmapi / kernel32）
    - macOS：系统自带 screencapture / osascript / system_profiler / ps
    - Linux：至少一个截图命令（maim / import / scrot / gnome-screenshot / xwd，Wayland 用 grim）；
             窗口枚举需要 wmctrl 或 xdotool（X11），或 swaymsg / hyprctl（Wayland）
    - Pillow（可选）：--scale 缩放、非 PNG 输出、输出到 stdout。

常用命令：
    python screen_fetch.py --list                       # 列出可截图窗口
    python screen_fetch.py -t 记事本 -o shot.png        # 按标题子串截图
    python screen_fetch.py -e notepad.exe --client      # 按进程名，只截客户区
    python screen_fetch.py --hwnd 0x123456 --method screen --activate
    python screen_fetch.py --region 0,0,800,600 -o r.png
    python screen_fetch.py --monitor 0 -o mon0.png
    python screen_fetch.py -t Chrome --count 20 --interval 0.5 -o "frames/f{i}.png"

平台差异：
    - Windows 支持 print / bitblt / screen 三种方式；macOS/Linux 统一走屏幕截图。
    - --hwnd：Windows 是 HWND；X11 是 window id；Sway 是 con_id；Hyprland 是 address；
      macOS 为内部编号（pid:序号），建议直接按标题/进程筛选。
    - --client：Windows 与 X11 精确；macOS 忽略，Wayland 忽略。
    - 退出码：0 成功，1 失败，2 无匹配窗口。
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sf_common import ScreenFetchError, warn  # noqa: E402

IS_WINDOWS = sys.platform == "win32"
IS_MACOS = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")

try:
    from PIL import Image
except Exception:  # Pillow 非必需
    Image = None

_BACKEND = None


def get_backend():
    global _BACKEND
    if _BACKEND is not None:
        return _BACKEND
    if IS_WINDOWS:
        from sf_win32 import WindowsBackend

        _BACKEND = WindowsBackend()
    elif IS_MACOS:
        from sf_darwin import DarwinBackend

        _BACKEND = DarwinBackend()
    elif IS_LINUX:
        from sf_linux import LinuxBackend

        _BACKEND = LinuxBackend()
    else:
        raise ScreenFetchError("不支持的平台：%s" % sys.platform)
    return _BACKEND


# --------------------------------------------------------------------------- #
# 保存
# --------------------------------------------------------------------------- #


def _format_for(path):
    ext = os.path.splitext(path)[1].lower()
    return {
        ".png": "PNG",
        ".jpg": "JPEG",
        ".jpeg": "JPEG",
        ".bmp": "BMP",
        ".webp": "WEBP",
        ".tif": "TIFF",
        ".tiff": "TIFF",
    }.get(ext)


def _write_bmp(path, data, width, height):
    """无 Pillow 时的兜底：手写 32bpp 自下而上 BMP。"""
    row = width * 4
    pixel_bytes = bytearray()
    for y in range(height - 1, -1, -1):
        pixel_bytes += data[y * row:(y + 1) * row]
    pixels = bytes(pixel_bytes)

    header = bytearray()
    header += b"BM"
    header += (14 + 40 + len(pixels)).to_bytes(4, "little")
    header += (0).to_bytes(4, "little")
    header += (14 + 40).to_bytes(4, "little")
    header += (40).to_bytes(4, "little")
    header += width.to_bytes(4, "little", signed=True)
    header += height.to_bytes(4, "little", signed=True)
    header += (1).to_bytes(2, "little")
    header += (32).to_bytes(2, "little")
    header += (0).to_bytes(4, "little")  # BI_RGB
    header += len(pixels).to_bytes(4, "little")
    header += (2835).to_bytes(4, "little")
    header += (2835).to_bytes(4, "little")
    header += (0).to_bytes(4, "little")
    header += (0).to_bytes(4, "little")

    with open(path, "wb") as fh:
        fh.write(header)
        fh.write(pixels)


def _save_from_file(frame, path, fmt, scale):
    source = frame.path
    if Image is None:
        if path == "-":
            with open(source, "rb") as fh:
                shutil.copyfileobj(fh, sys.stdout.buffer)
            return "-"
        if abs(scale - 1.0) > 1e-9:
            warn("未安装 Pillow，--scale 被忽略（pip install pillow 可启用）")
        target = path
        if fmt not in (None, "PNG"):
            warn("未安装 Pillow，改为写出 PNG：%s" % path)
            target = os.path.splitext(path)[0] + ".png"
        if os.path.abspath(source) != os.path.abspath(target):
            parent = os.path.dirname(target)
            if parent:
                os.makedirs(parent, exist_ok=True)
            shutil.move(source, target)
        return target

    with Image.open(source) as opened:
        img = opened.copy()
    if fmt == "JPEG" and img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    if scale and abs(scale - 1.0) > 1e-9:
        new_size = (max(1, round(img.width * scale)), max(1, round(img.height * scale)))
        img = img.resize(new_size, Image.LANCZOS)
    if path == "-":
        img.save(sys.stdout.buffer, format="PNG")
        return "-"
    if fmt is None:
        path = os.path.splitext(path)[0] + ".png"
        fmt = "PNG"
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    img.save(path, format=fmt)
    return path


def _save_bgra(frame, path, fmt, scale):
    data = frame.bgra
    if Image is None:
        if path == "-":
            raise ScreenFetchError("没有 Pillow 时不能输出到 stdout")
        if abs(scale - 1.0) > 1e-9:
            warn("未安装 Pillow，--scale 被忽略（pip install pillow 可启用）")
        if fmt not in (None, "BMP"):
            warn("未安装 Pillow，改为写出 BMP：%s" % path)
            path = os.path.splitext(path)[0] + ".bmp"
        _write_bmp(path, data, frame.width, frame.height)
        return path

    img = Image.frombuffer("RGB", (frame.width, frame.height), data, "raw", "BGRX", 0, 1)
    if scale and abs(scale - 1.0) > 1e-9:
        new_size = (max(1, round(frame.width * scale)), max(1, round(frame.height * scale)))
        img = img.resize(new_size, Image.LANCZOS)

    if path == "-":
        img.save(sys.stdout.buffer, format="PNG")
        return "-"
    if fmt is None:
        path = os.path.splitext(path)[0] + ".png"
        fmt = "PNG"
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    img.save(path, format=fmt)
    return path


def save_frame(frame, path, scale=1.0):
    """保存截图，返回真正写出的文件路径（stdout 时返回 '-'）。"""
    path = os.path.abspath(path) if path != "-" else "-"
    fmt = _format_for(path) if path != "-" else None
    if frame.path:
        return _save_from_file(frame, path, fmt, scale)
    return _save_bgra(frame, path, fmt, scale)


# --------------------------------------------------------------------------- #
# 选择窗口
# --------------------------------------------------------------------------- #


def find_windows(args):
    title_pat = None
    if args.title:
        title_pat = re.compile(args.title if args.regex else re.escape(args.title), re.IGNORECASE)
    class_pat = None
    if args.cls:
        class_pat = re.compile(args.cls if args.regex else re.escape(args.cls), re.IGNORECASE)
    exe_pat = None
    if args.exe:
        exe_pat = re.compile(re.escape(os.path.basename(args.exe)), re.IGNORECASE)

    matches = []
    for win in get_backend().list_windows(include_hidden=args.include_hidden):
        if not args.include_hidden:
            if not win.visible:
                continue
            if not win.title:
                continue
        if args.pid is not None and win.pid != args.pid:
            continue
        if title_pat and not title_pat.search(win.title):
            continue
        if class_pat and not class_pat.search(win.cls):
            continue
        if exe_pat and not exe_pat.search(win.exe):
            continue
        matches.append(win)
    return matches


def select_window(args):
    if args.hwnd:
        return get_backend().window_by_id(args.hwnd)

    matches = find_windows(args)
    if not matches:
        raise ScreenFetchError("没有匹配的窗口（试试 --list 查看）")
    if len(matches) > 1 and not args.first and args.index is None:
        lines = ["匹配到 %d 个窗口，请用 --index N / --first / --hwnd 精确指定：" % len(matches)]
        for i, w in enumerate(matches[:20]):
            lines.append(
                "  [%d] hwnd=%s pid=%-6d %-24s %s"
                % (i, w.as_dict()["hex"], w.pid, (w.cls or "")[:24], w.title[:60])
            )
        if len(matches) > 20:
            lines.append("  ...")
        raise ScreenFetchError("\n".join(lines))
    if args.index is not None:
        if not (0 <= args.index < len(matches)):
            raise ScreenFetchError(
                "--index 越界：共 %d 个匹配（0..%d）" % (len(matches), len(matches) - 1)
            )
        return matches[args.index]
    return matches[0]


# --------------------------------------------------------------------------- #
# 输出格式
# --------------------------------------------------------------------------- #


def _fmt_window(win, index=None):
    x, y, w, h = win.rect
    flags = []
    if win.minimized:
        flags.append("min")
    if not win.visible:
        flags.append("hidden")
    tag = ("[%d] " % index) if index is not None else ""
    wid = win.as_dict()["hex"]
    return "%-5s%-14s%-7d%-27s%4dx%-5d @%d,%d  %-22s %s%s" % (
        tag,
        wid[:14],
        win.pid,
        (win.cls or "")[:26],
        w,
        h,
        x,
        y,
        (win.exe or "")[:22],
        win.title[:60],
        ("  <" + ",".join(flags) + ">") if flags else "",
    )


def cmd_list(args):
    wins = find_windows(args)
    wins.sort(key=lambda w: (w.pid, str(w.hwnd)))
    if args.json:
        print(json.dumps([w.as_dict() for w in wins], ensure_ascii=False, indent=2))
        return 0
    print(
        "%-5s%-14s%-7s%-27s%-10s%-12s%-23s%s"
        % ("", "WINDOW", "PID", "CLASS", "SIZE", "POS", "EXE", "TITLE")
    )
    for i, win in enumerate(wins):
        print(_fmt_window(win, i))
    print("\n共 %d 个窗口" % len(wins))
    return 0


def cmd_list_monitors(args):
    mons = get_backend().list_monitors()
    if args.json:
        print(json.dumps([{k: v for k, v in m.items() if k != "handle"} for m in mons], indent=2))
        return 0
    for m in mons:
        x, y, r, b = m["rect"]
        print(
            "[%d] %s%s  %dx%d @%d,%d  (work %dx%d)"
            % (
                m["index"],
                m["device"],
                " *primary" if m["primary"] else "",
                r - x,
                b - y,
                x,
                y,
                m["work"][2] - m["work"][0],
                m["work"][3] - m["work"][1],
            )
        )
    return 0


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #


def build_parser():
    p = argparse.ArgumentParser(
        prog="screen_fetch.py",
        description="跨平台窗口/屏幕截图（Windows / macOS / Linux）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""示例:
  python screen_fetch.py --list
  python screen_fetch.py -t 记事本 -o shot.png
  python screen_fetch.py -e notepad.exe --client --method print
  python screen_fetch.py --hwnd 0x1A2B3C --activate --method screen
  python screen_fetch.py --region 0,0,800,600 -o region.png
  python screen_fetch.py --monitor 0 -o mon0.png
  python screen_fetch.py -t Chrome --count 20 --interval 0.5 -o "frames/f{i}.png"
""",
    )

    g = p.add_argument_group("窗口选择")
    g.add_argument("-l", "--list", action="store_true", help="列出窗口后退出")
    g.add_argument("--list-monitors", action="store_true", help="列出显示器后退出")
    g.add_argument("--hwnd", help="窗口 ID（HWND / X11 window id / Sway con_id / Hyprland address）")
    g.add_argument("-t", "--title", help="标题子串（加 --regex 用正则）")
    g.add_argument("-c", "--class", dest="cls", help="窗口类名/应用名子串")
    g.add_argument("-p", "--pid", type=int, help="进程 ID")
    g.add_argument("-e", "--exe", help="进程可执行文件名，如 notepad.exe / chrome")
    g.add_argument("--regex", action="store_true", help="--title/--class 按正则匹配")
    g.add_argument("--include-hidden", action="store_true", help="包含隐藏/无标题窗口")
    g.add_argument("--index", type=int, help="多个匹配时选第 N 个")
    g.add_argument("--first", action="store_true", help="多个匹配时直接取第一个")

    g = p.add_argument_group("截图")
    g.add_argument("-m", "--method", default="auto",
                   choices=["auto", "print", "bitblt", "screen"],
                   help="截图方式；print/bitblt 仅 Windows，其余平台等同 screen")
    g.add_argument("--client", action="store_true", help="只截客户区（Windows/X11 支持）")
    g.add_argument("--activate", action="store_true", help="截图前把窗口还原并置前")
    g.add_argument("--print-flags", type=lambda s: int(s, 0), default=2,
                   help="Windows PrintWindow 的 flags，默认 0x2 (RENDERFULLCONTENT)")
    g.add_argument("--region", help="直接截屏幕区域 x,y,w,h")
    g.add_argument("--monitor", type=int, help="截第 N 个显示器（见 --list-monitors）")
    g.add_argument("--scale", type=float, default=1.0, help="输出缩放系数（需 Pillow）")
    g.add_argument("--delay", type=float, default=0.0, help="截图前等待秒数")
    g.add_argument("--count", type=int, default=1, help="连拍张数")
    g.add_argument("--interval", type=float, default=0.5, help="连拍间隔秒")

    g = p.add_argument_group("输出")
    g.add_argument("-o", "--output", default="screen_fetch_{time}.png",
                   help="输出路径，支持 {time}/{i}，'-' 表示写 PNG 到 stdout")
    g.add_argument("--json", action="store_true", help="把结果元数据打印为 JSON")
    g.add_argument("--print-hwnd", action="store_true", help="只打印选中窗口的 ID")
    g.add_argument("-q", "--quiet", action="store_true", help="不打印成功信息")
    return p


def _expand_output(template, index, count):
    name = template.replace("{time}", _dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3])
    if count > 1:
        if "{i}" in template:
            name = name.replace("{i}", "%03d" % index)
        else:
            root, ext = os.path.splitext(name)
            name = "%s_%03d%s" % (root, index, ext)
    else:
        name = name.replace("{i}", "000")
    return name


def _parse_region(text):
    parts = [p.strip() for p in text.split(",")]
    if len(parts) != 4:
        raise ScreenFetchError("--region 需要 x,y,w,h 四个整数，例如 0,0,800,600")
    try:
        x, y, w, h = (int(p, 0) for p in parts)
    except ValueError:
        raise ScreenFetchError("--region 含有非数字：%s" % text)
    return x, y, w, h


def run(args):
    backend = get_backend()
    target = None
    monitor_index = None
    area = None

    if args.region:
        area = _parse_region(args.region)
        desc = "region %d,%d %dx%d" % area
    elif args.monitor is not None:
        mons = backend.list_monitors()
        if not (0 <= args.monitor < len(mons)):
            raise ScreenFetchError("--monitor 越界：共 %d 个显示器" % len(mons))
        monitor_index = args.monitor
        area = tuple(mons[monitor_index]["rect"])
        desc = "monitor %d (%s)" % (monitor_index, mons[monitor_index]["device"])
    else:
        target = select_window(args)
        desc = "hwnd=%s pid=%d %s" % (
            target.as_dict()["hex"],
            target.pid,
            target.title[:60],
        )

    if args.print_hwnd and target is not None:
        print(target.as_dict()["hex"])
        return 0

    if args.count < 1:
        raise ScreenFetchError("--count 至少为 1")
    if args.output == "-" and args.count > 1:
        raise ScreenFetchError("--output - 时不能连拍")

    if args.delay > 0:
        time.sleep(args.delay)
    if args.activate and target is not None:
        backend.activate(target)

    results = []
    for i in range(args.count):
        started = time.perf_counter()
        frame = None
        if target is not None:
            if args.activate and i > 0:
                backend.activate(target)
            frame = backend.capture_window(
                target, method=args.method, client=args.client, flags=args.print_flags
            )
        elif monitor_index is not None:
            frame = backend.capture_monitor(monitor_index)
        else:
            frame = backend.capture_rect(*area)
        elapsed = (time.perf_counter() - started) * 1000.0

        if (
            i == 0
            and target is not None
            and frame.method == "screen"
            and backend.name == "windows"
            and not backend.is_foreground(target)
            and not args.quiet
        ):
            warn("screen 方式抓取的是屏幕像素，目标窗口不在前台，可能截到覆盖它的窗口")
            warn("需要完整窗口内容可加 --activate（或改用 --method print）")

        try:
            out_path = _expand_output(args.output, i, args.count)
            written = save_frame(frame, out_path, scale=args.scale)
            width, height = frame.width, frame.height
        finally:
            frame.cleanup()

        result = {
            "file": written,
            "width": width,
            "height": height,
            "method": frame.method,
            "elapsed_ms": round(elapsed, 1),
            "target": target.as_dict() if target is not None else desc,
        }
        results.append(result)

        if not args.quiet and args.output != "-":
            if args.json:
                print(json.dumps(result, ensure_ascii=False))
            else:
                print(
                    "已保存 %s  %dx%d  method=%s  %.1fms  %s"
                    % (written, width, height, frame.method, elapsed, desc)
                )

        if i + 1 < args.count:
            time.sleep(max(0.0, args.interval))

    if args.json and args.count > 1:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except Exception:
            pass

    args = build_parser().parse_args(argv)

    try:
        if args.list:
            return cmd_list(args)
        if args.list_monitors:
            return cmd_list_monitors(args)
        return run(args)
    except ScreenFetchError as exc:
        print("错误：%s" % exc, file=sys.stderr)
        return 2 if ("没有匹配" in str(exc)) else 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
