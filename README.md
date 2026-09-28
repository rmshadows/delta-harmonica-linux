# delta-harmonica（三角洲口琴练习辅助 · Linux）

Linux 命令行工具：解析记事本简谱（及 MIDI 转简谱），配合 scrcpy 投屏做口琴界面上的**练习辅助**。

> 请先进入游戏口琴界面，再使用本工具。仅供个人练习与乐谱整理，请遵守游戏规则与当地法律。

## 依赖

- Python 3.11+
- [Android platform-tools](https://developer.android.com/tools/adb)（`adb`）
- [scrcpy](https://github.com/Genymobile/scrcpy)（投屏观看；标定时代捕获窗口点击）
- X11 环境推荐（标定依赖窗口几何；Wayland 下可能受限）
- 可选：`xdotool`（用于自动查找 scrcpy 窗口）

## 入口（推荐）

仓库根目录有包装脚本，**一般不用每次手动建 venv / activate**：

```bash
cd delta-harmonica-linux
./dharm doctor
./dharm preview
./dharm play tonghua -p myphone --dry-run
```

第一次运行会自动创建 `.venv` 并 `pip install -e .`；之后直接 `./dharm …` 即可。

若你更习惯传统方式：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
dharm --help
```

## 快速流程

1. 手机开启 USB 调试，连接电脑，启动 scrcpy。
2. 进入游戏口琴界面。
3. 标定按键坐标（每个机型做一次）：

```bash
dharm doctor
dharm calibrate --profile myphone
dharm calibrate --profile myphone --test
```

标定存的是**手机屏幕坐标**（adb 触摸坐标），不是 scrcpy 窗口像素。窗口最大化/缩小/移动都不用重标定；只有分辨率、横竖屏或游戏 UI 布局变了才需要。

4. 选择或编写乐谱，开始练习辅助：

```bash
dharm list
dharm play example -p myphone
dharm play scores/example.txt -p myphone --dry-run   # 只打印时间轴
```

默认参数写在仓库根目录 [`dharm.toml`](dharm.toml)（可用 `-H` / `-E` / `-p` 临时覆盖）：

```toml
profile = "z60u"
press_early = 120   # 模式1：下一音提前按下（更连贯）
hold_extra = 200    # 模式2：每个音多按住（等游戏出声）
speed = 1.0         # 初始倍速；播放中 +/- 或 ]/[ 可调，q 停止
countdown = 1
```

```bash
dharm play beijiaer
# 播放中：+ / ] 加速，- / [ 减速，q 停止
```

Shell 自动补全（命令 / 乐谱名 / profile）：

```bash
# 推荐：加载仓库自带的补全（支持 ./dharm 与 dharm）
# zsh — 写入 ~/.zshrc 一次即可：
echo "source $(pwd)/completions/dharm.zsh" >> ~/.zshrc
source ~/.zshrc

# 或用 Typer 自带安装（只注册命令名 dharm，需 PATH 含 .venv/bin）
./dharm --install-completion
```

用法：乐谱放在**最后**：

```bash
./dharm play -p z60u beijiaer
./dharm -p z60u play scores/beijiaer.txt
./dharm play beijiaer          # dharm.toml 已设 profile 时可省略 -p
```

5. （推荐）电脑上先听谱预览，再上手游：

```bash
dharm preview
# 浏览器打开后可播放 / 改谱 / 打开 scores/*.txt
```

6. （可选）从 MIDI 生成简谱草稿：

```bash
dharm midi2txt song.mid -o scores/song.txt --bpm 96
```

## 乐谱格式（txt）

见 [`scores/example.txt`](scores/example.txt)。要点：

- 元数据：`title` / `bpm` 或 `ms_beat`
- 音高：`1`–`7`，同排高音 `1'`（界面第 8 键 `1̇`；`#1` 播放时也会打到这一键）
- 修饰（跟游戏一致）：`s1` 半音(+1)、`#2`…`#7` 升调(+八度)、`b1` 降调(-八度)；`##1` = 升调+`1'`（再高八度）；自然音为默认
- 时值：`/4` `/8` `/16` `/2`（默认 `/4`）
- 休止：`0/4` 或 `-`
- `0` / `0/8` / `0:350` 休止（`0:毫秒`=精确停顿）；`rest_scale:` 整体缩放休止
- `|` 仅小节线；`/4.` 附点；`> 歌词` 标句
- 连音线：`+` 连接（同音合并时值，如 `#5/16+#5/8`；异音依次演奏）；也可直接写成附点/`5/2.`
- 预览：滚轮调速（仅速度行）、进度条、句高亮；数字键录音符，Q/W/E=半音/降八度/升八度

## 命令一览

| 命令 | 说明 |
|------|------|
| `dharm doctor` | 检查 adb / scrcpy / 设备 |
| `dharm calibrate -p NAME` | 在 scrcpy 窗口上依次点击标定 |
| `dharm calibrate -p NAME --test` | 按标定依次触达各键（听音确认） |
| `dharm list` | 列出 `scores/` 下乐谱 |
| `dharm play SCORE [-p NAME]` | 练习辅助；`[/]` 调速、`←→` 调（CDEFGAB）、`↑↓` ±八度、`z/x` early±50、`c/v` hold±50、`s` 写入乐谱 |
| `dharm --install-completion` | 安装 shell 自动补全 |
| `dharm midi2txt FILE.mid` | MIDI → txt 草稿 |
| `dharm preview` | 浏览器听谱预览（不连手机） |

## 目录

- `scores/` — 默认乐谱（童话、大悲咒、冲锋号、Lemon、我愿意、千与千寻、歌唱祖国、在希望的田野上、贝加尔湖畔、蓝调小品等）
- `preview/` — PC 端 HTML 听谱预览
- `profiles/` — 标定结果（本机坐标，默认不提交）
- `dharm.toml` — 默认 `profile` / `press_early` / `hold_extra` / `countdown`（倍速和调写在各乐谱 `speed:` / `transpose:`）

## 限制

- 需要 USB 调试；不同机型分辨率必须重新标定。
- 触控优先使用 `adb shell input motionevent`；不支持时回退 `swipe`（时值精度略差）。
- scrcpy 窗口黑边/缩放会影响标定，标定后请 `--test`。
- 听谱预览为简易 Web Audio，仅供对谱；不做 OCR 找键。

## 许可

见 [LICENSE](LICENSE)。
