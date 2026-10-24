# window-capture skill

跨平台窗口 / 屏幕截图技能：用系统 API 或系统自带工具直接截图，把 PNG 交给 AI 编码代理的图片读取能力，形成 GUI 开发的视觉反馈闭环。

支持：

- Windows（纯标准库 ctypes，调用 user32/gdi32/dwmapi）
- macOS（screencapture / osascript，需要屏幕录制与辅助功能权限）
- Linux X11（maim / import / scrot / gnome-screenshot，wmctrl / xdotool）
- Linux Wayland（grim + swaymsg / hyprctl）

## 安装

把本仓库内容放到代理的技能目录中即可，例如：

```powershell
# Windows
git clone https://github.com/sakurainn/window-capture-skill "$env:USERPROFILE\.agents\skills\window-capture"
```

```bash
# Linux / macOS
git clone https://github.com/sakurainn/window-capture-skill ~/.agents/skills/window-capture
```

也可以直接克隆到 `~/.claude/skills/window-capture`，SKILL.md 中的 front matter 会被自动识别。

## 使用

```bash
export PYTHONUTF8=1
python scripts/screen_fetch.py --list
python scripts/screen_fetch.py --window "窗口标题" -o shot.png
```

```powershell
$env:PYTHONUTF8 = "1"
python scripts/screen_fetch.py --list
python scripts/screen_fetch.py --window "窗口标题" -o shot.png
```

完整参数与平台说明见 [SKILL.md](SKILL.md)。

## 目录结构

```
SKILL.md              # 技能说明与代理工作流
scripts/
  screen_fetch.py     # 命令行入口
  sf_common.py        # 公共工具
  sf_win32.py         # Windows 后端
  sf_darwin.py        # macOS 后端
  sf_linux.py         # Linux（X11 / Wayland）后端
```

## License

MIT
