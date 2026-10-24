---
name: window-capture
description: Use when developing, debugging, or verifying a GUI app and you need to actually see it; cross-platform (Windows/macOS/Linux) capture of app windows, client areas, screen regions, monitors, or animation bursts with screen_fetch.py, then inspect the PNG with the Read tool. Trigger keywords: screen_fetch.py, 窗口截图, 屏幕截图, 界面截图, 截图看一下, screenshot, window capture, capture window, GUI 调试, 界面验证, 布局检查, macOS 截图, Linux 截图.
---

# 窗口捕获（screen_fetch.py）

用系统 API/工具直接截图，再把 PNG 交给 Read 工具“看”，形成 GUI 开发的视觉反馈闭环。
支持 Windows / macOS / Linux（X11，以及 sway/Hyprland 等 wlroots Wayland）。
Windows 纯标准库；macOS/Linux 依赖系统自带或常见的截图命令；Pillow 可选。

脚本位置：`scripts/screen_fetch.py`（相对于本 SKILL.md 所在目录）。

在 PowerShell 里先设变量，后续命令直接复用（先进入本 SKILL.md 所在目录）：

```powershell
$env:PYTHONUTF8 = "1"   # 必须：否则中文窗口标题在控制台会乱码
$SF = (Resolve-Path "scripts/screen_fetch.py").Path   # 相对技能目录解析
python $SF --list
```

bash/zsh 等价写法：

```bash
export PYTHONUTF8=1
SF=scripts/screen_fetch.py   # 在技能目录下执行
python "$SF" --list
```

## 平台依赖

| 平台 | 需要 | 说明 |
| --- | --- | --- |
| Windows | 无 | ctypes 调用 user32/gdi32/dwmapi |
| macOS | screencapture、osascript、system_profiler（系统自带） | 首次使用需到 系统设置 > 隐私与安全性 授予“屏幕录制”和“辅助功能” |
| Linux X11 | 截图：maim 或 ImageMagick(import) 或 scrot 或 gnome-screenshot；枚举：wmctrl 或 xdotool | 推荐 `sudo apt install maim wmctrl` |
| Linux Wayland | grim；枚举：swaymsg 或 hyprctl | GNOME/KDE Wayland 仅支持全屏（spectacle/gnome-screenshot） |

## GUI 开发闭环（推荐流程）

1. 启动/重启应用并等窗口出现（`--delay` 或先启动进程）。
2. `--list` 找到目标窗口，确认 EXE / 标题 / 类名唯一。
3. 用 `--client` 截客户区（Windows/X11 支持；macOS/Wayland 会退化为整窗）。
4. 固定输出到临时目录，然后用 Read 工具直接读图片判断布局、文字、状态。
5. 改代码 → 重建 → 用完全相同的命令重截 → 对比。

```powershell
# Windows
Start-Process .\build\app.exe
python $SF -e app.exe --delay 2 --client -o "$env:TEMP\opencode\gui.png"
```

```bash
# macOS / Linux
./build/app &
python "$SF" -e app --delay 2 --client -o "${TMPDIR:-/tmp}/opencode/gui.png"
```

然后用 Read 打开实际输出路径（`$env:TEMP\opencode` / `${TMPDIR:-/tmp}/opencode` 通常已预授权）。
输出路径固定，便于连续对比；不要截到项目目录里。

## 选窗口

| 参数 | 作用 |
| --- | --- |
| `-t 子串` | 标题子串匹配；加 `--regex` 可用正则 |
| `-e app.exe` | 按可执行文件名匹配（basename 精确） |
| `-p 1234` | 按 PID |
| `--hwnd ID` | 精确窗口 ID（见下） |
| `--class 类名` | 按窗口类名/应用名匹配 |
| `--index N` / `--first` | 多匹配时选第 N 个 / 取第一个 |
| `--include-hidden` | 连隐藏/无标题窗口一起列出 |

- `--hwnd`：Windows 是 HWND（支持 `0x`）；X11 是 window id；Sway 是 con_id；Hyprland 是 address；macOS 用内部编号 `pid:序号`，建议直接用标题/进程筛选。
- 多匹配时脚本会报错并列出候选，退出码为 2；按提示加 `--index` 或 `--hwnd`。
- `--print-hwnd` 只输出 ID；`--json` 输出元数据（含 rect/pid/method），适合管道处理。
- macOS 的 `--class` 匹配的是应用名，`-e` 匹配的是进程可执行文件。

## 选截图方式

| `--method` | 适合 | 限制 |
| --- | --- | --- |
| `auto`（默认） | Windows：PrintWindow 失败自动回退屏幕；其他平台等同 `screen` | — |
| `print` | Windows 被遮挡、后台窗口 | GPU/DirectX 窗口（Chrome/Electron、游戏、模拟器）常全黑 |
| `bitblt` | Windows 需要 GPU 内容 | 窗口被遮挡时会截到遮挡物 |
| `screen` | 最稳、所见即所得；全平台可用 | 必须可见且在前台，建议配 `--activate` |

- `print` / `bitblt` 仅 Windows 生效；macOS/Linux 会自动改用屏幕截图。
- `--client`：Windows 与 X11（xwininfo）精确；macOS/Wayland 会忽略并警告。
- `--activate`：截图前还原并置前；Windows 用 Win32，X11 用 wmctrl，Wayland 用 swaymsg/hyprctl，macOS 用 System Events。
- `--delay N`：等界面渲染/动画结束再截。
- `--scale 0.5`：缩小图片，省视觉 token（需 Pillow）；stdout 打印的宽高是缩放前的原始尺寸。
- 怀疑截到黑图时，改用 `--method screen --activate` 验证一次。

## 常用配方

```powershell
# 后台或被遮挡的窗口（Windows）
python $SF -t "设置" --method print --client -o "$env:TEMP\opencode\a.png"

# Chrome / Electron / 游戏 / 模拟器（GPU 渲染）
python $SF -e chrome.exe --activate --method screen --client -o "$env:TEMP\opencode\b.png"

# 指定屏幕区域（绝对屏幕坐标，可为负）或整块显示器
python $SF --region 0,0,800,600 -o "$env:TEMP\opencode\r.png"
python $SF --monitor 0 -o "$env:TEMP\opencode\m0.png"
python $SF --list-monitors

# 连拍：动画、悬停、过渡、加载状态
python $SF -e app.exe --client --count 20 --interval 0.2 -o "$env:TEMP\opencode\f{i}.png"

# 只看元数据 / ID
python $SF -e app.exe --json
python $SF -e app.exe --print-hwnd
```

Linux/macOS 把 `$env:TEMP\opencode` 换成 `"${TMPDIR:-/tmp}/opencode"`，可执行名按 `--list` 结果填写。

## 陷阱

- Windows：最小化窗口先 `--activate`（脚本会 `ShowWindow(SW_RESTORE)`）；程序是 Per-Monitor DPI 感知，坐标均为物理像素。
- macOS：截图返回的是物理像素，而 `--region`/窗口坐标是逻辑点，Retina 屏上两者相差缩放倍率，不要混用。
- macOS：没有“屏幕录制”权限时 `screencapture` 可能返回全黑/失败；没有“辅助功能”权限时枚举窗口会失败。
- macOS：`--hwnd` 是内部编号，窗口重新打开后可能变化；优先按标题/进程筛选。
- Linux X11：`--class` 来自 wmctrl，通常是 `实例.类名`；未安装截图工具时脚本会给出安装提示。
- Linux Wayland：窗口/区域截图需要 grim 且合成器为 wlroots 系（sway/Hyprland）；GNOME/KDE 下只能全屏。
- `--region` 是屏幕绝对坐标，多显示器副屏在左侧时 x 为负；Windows 上按物理像素，macOS 上按逻辑点。
- 无 Pillow 时：Windows 退化为 BMP；macOS/Linux 直接透传系统工具生成的 PNG，`--scale` 失效。
- `-o -` 是把 PNG 写到 stdout，不要配合图片 Read 使用，始终写文件。
- 用 `screen` 方式时若目标不在前台，可能截到覆盖它的窗口，此时加 `--activate`。
- 截完只在临时目录留最近几张，避免堆积；需要基线对比时把旧的复制成 `baseline.png`。

## 像素对比（可选，验证只改了预期区域）

```powershell
python -c "from PIL import Image, ImageChops; a=Image.open(r'$env:TEMP\opencode\baseline.png').convert('RGB'); b=Image.open(r'$env:TEMP\opencode\gui.png').convert('RGB'); d=ImageChops.difference(a,b); print('bbox', d.getbbox()); print('changed', sum(1 for p in d.getdata() if p!=(0,0,0)), '/', a.width*a.height)"
```

先 Read 两张图肉眼确认，再用 bbox 判断改动范围是否符合预期。
