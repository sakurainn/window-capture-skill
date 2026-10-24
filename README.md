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

## 用 npx 直接用（无需克隆）

需要本机已安装 Python 3。npx 会临时拉取仓库并转发参数给 `screen_fetch.py`：

```bash
npx --yes git+https://github.com/sakurainn/window-capture-skill --list
npx --yes git+https://github.com/sakurainn/window-capture-skill --window "窗口标题" -o shot.png
```

也可以用 `npm i -g git+https://github.com/sakurainn/window-capture-skill` 安装出全局命令 `window-capture-skill`。发布到 npm 之后即可简写为 `npx window-capture-skill ...`。

> 注意：直接写 `npx github:sakurainn/window-capture-skill` 时 npm 会走 SSH（`git@github.com`），没配置密钥会失败；请用上面的 `git+https` 形式。

默认依次尝试 `python` / `py -3`（Windows）或 `python3` / `python`（macOS / Linux），也可用环境变量 `WINDOW_CAPTURE_PYTHON` 指定解释器。

## 使用（本地克隆）

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
bin/
  window-capture.js   # npx / 全局安装入口（转发到 Python）
scripts/
  screen_fetch.py     # 命令行入口
  sf_common.py        # 公共工具
  sf_win32.py         # Windows 后端
  sf_darwin.py        # macOS 后端
  sf_linux.py         # Linux（X11 / Wayland）后端
```

## License

MIT
