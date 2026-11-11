# 包内字幕模板与成片检查

六套字幕模板已随包提供，使用者无需 Git、GitHub 登录、仓库权限或下载源码。字体与许可证也已包含。安装一次 `packaging` 依赖：

```sh
# Mac，在本 Skill 目录运行
sh ./install.sh packaging
sh ./check-env --with-captions
```

```powershell
# Windows，原生 PowerShell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 packaging
.\check-env.ps1 --with-captions
```

脚本优先使用具备 libass 的本机 FFmpeg；缺少时使用 `imageio-ffmpeg` 安装的本地可执行文件。可用 `--ffmpeg` 或 `VIDEO_WORKFLOW_FFMPEG` 指定本机路径。FFprobe 仍须在 PATH。安装依赖需要联网，运行模板不访问仓库或外部服务。

## 直接说

> 用 video-workflow-starter，为这条成片应用包内 D 字幕样式，保留审定稿的大小写和标点。画面用全屏竖版，头部安全时保持不动。检查字幕位置、静音口型和结尾，输出到新目录。

Agent 先读 [制作规则](production-rules.md)，核对真实音频对齐和画面，再执行：

```sh
python3 workflow.py captions --video "成片.mp4" --words "词级对齐.json" \
  --approved-text "审定稿.txt" --language en --template D --out "新的包装目录"
```

Windows 将 `python3` 换为 `python`。`--words` 使用 WhisperX/stable-whisper 风格的真实词级数据：`{"segments":[{"words":[{"word":"Hello,","start":0.1,"end":0.5}]}]}`。本例仅表示格式，不是对齐证据。用包内 `align` 对齐时，读取其缓存的完整 `full.json`；应用锚点修订后须采用修订后的词级时间戳，不能沿用旧缓存。无可靠词级对齐就停在句级字幕路线，不伪造词时长。

`captions` 校验词级文字与审定稿一致、时间戳有效，调用随包的 `apply_template.py`，输出 `final.mp4`、`final.ass`、预览图、日志和 `receipt.json`，拒绝覆盖已有输出目录。回执的 `technical_pass_visual_review_pending` 只表示技术检查通过。还需观看人脸、字幕、口型并测量响度。

完整保留 A–F 供了解模板能力；本工作流使用 B–F 全屏版。A 的横版窗口布局不符合默认要求，入口拒绝它。入口默认关掉自动推拉和节奏放大，保留大小写与标点，暂不添加会挡住前段字幕的 F 开场文字。需要更改字号、字体或分句长度时复制所选 `specs/*.json` 到项目目录，用 `--spec` 指定。模板字体覆盖拉丁、西里尔和中文；其他文字须自行配置具备授权的字体并检查字形。

模板目前只执行居中固定竖裁。先用安全固定竖裁副本作为输入可保留偏移构图；自动平滑跟随尚未泛化入此入口，遇到头部出框风险应在已有剪辑软件处理后继续，不宣称脚本已自动解决。

## Mac 可选视觉检查

以下两个入口复用本地已用过的 Python + Swift/Vision 脚本。需要 macOS 和 Xcode Command Line Tools（`xcode-select --install`），与基本切片/模板渲染分开安装。Windows 不执行这两项 Apple 检测，可人工检查同样规则。

```sh
sh ./check-env --with-visual-checks
python3 workflow.py frame-check "成片.mp4" "实际对齐.srt"
python3 workflow.py silent-mouth inspect "竖版成片.mp4" "实际对齐.srt" "新检查目录"
# 只有 inspect 回执明确 action=trim_tail 时执行：
python3 workflow.py silent-mouth trim "竖版成片.mp4" "实际对齐.srt" "同一检查目录"
python3 workflow.py silent-mouth verify "竖版成片.mp4" "实际对齐.srt" "同一检查目录"
```

`frame-check` 只给出构图建议，不渲染跟随。静音口型结果为 `review` 时不能自动裁切；缺失人脸、检测不足或中段问题保留复核。检测阈值来自既有实现，是候选值，不承诺通用于所有人物。原视频保留；剪尾另存，再看实际结果。

## 随包版本

模板 v1.4，提交 `2e8c0e06740f5a1e8fa21a7519ece85561bdc79a`。代码 MIT、字体 SIL OFL，见包内 LICENSE 和 fonts 的许可文件。母版仓库由维护者管理；升级通过新版 ZIP 交付，不要求使用者访问仓库。

本地适配：增加保留正文/固定构图/指定 FFmpeg 选项，UTF-8 和 Windows 滤镜路径转义，超时与不覆盖输出；字体、规格和 ASS 构建逻辑沿用原版。上游逐文件哈希见 `caption-upstream.json`。当前工作流要求优先于副本中的原始样式说明。

## 本包默认字幕字号（2.3.20）

以 1080×1920 画幅为基准：A 72、B 84、C 64、D 82、E 74、F 54。B 保持原字号，其余略增；只改口播字幕，不改标题、姓名条或开场大字。字幕仍居中、左右对称留白。不同语言长词可能需要断行或缩短每组字幕，不能删改审定稿。
