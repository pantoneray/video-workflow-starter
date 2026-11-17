# 安装与逐步使用：v2.3.22-rc.10

可以只用其中一个步骤，也可以按顺序完成制作。以下终端示例使用 Mac；Windows 使用包内 install.ps1，HeyGen 网页校对路线需 WSL，配置见 INTEGRATIONS.md。

## 1. 安装与项目配置

最方便的方法：把 [README安装提示词](README.md#复制给-codex开始安装) 发给本机 Codex。下载指定 Release 的完整 ZIP 与 `.sha256` 文件，核对后解压。将完整目录放入 `~/.codex/skills/video-workflow-starter/`，再安装；不要搬运已有虚拟环境。

以下终端指令在 Skill 目录运行。尖括号是占位符，需替换为本人的真实路径；也可让 Codex 代执行。

```bash
sh ./check-env
sh ./install.sh base
# 配置 config.example.json 的副本，保存到包外项目目录后：
python3 workflow.py project check --config <项目/video-config.json>
python3 workflow.py project init --config <项目/video-config.json> --project-root <项目目录>
# 已经初始化过的项目改用：
python3 workflow.py project sync --config <项目/video-config.json> --project-root <项目目录>
python3 workflow.py guide --config <项目/video-config.json>
```

基础依赖为 Python 3.9+、FFmpeg/FFprobe；本地音频对齐建议 Python 3.11/3.12。安装后让 Codex 执行环境检查和离线样本，确认需要的功能可运行。刷新或重启 Codex 加载 Skill。项目初始化会写入通用制作规则，保留既有 AGENTS.md 内容与个人备注。

## 2. 批量切片

作用：从文件夹完整扫描视频，寻找多条自然连续画面，调用 FFmpeg 裁切并检查输出。原片保留，输出写新目录。

> 用 video-workflow-starter 扫描这个文件夹，优先清晰源片，总共选10条30–45秒切片，每个原视频最多3条，同时扫描2个视频。按规则检查动作与自然起止，合格不足就如实报告，输出到新目录，给我播放检查。

脚本参考：`python3 workflow.py batch-clips --help`。机械检测不代替完整动作审核，不保证只靠脚本识别所有遮挡、手势和低头。

## 3. 选文与翻译

作用：从本人资料库按主题找原文，保留出处与上下文；逐语种形成译稿、盲回译和校对结果。

> 列出我的主题库供我选择，从指定资料中找有出处且适合独立理解的候选。新主题先问我是否保存。原文通过后翻译为我选的语言，Google Translate做盲回译、Gemini做独立校对。把完整审稿材料放在本次输出的“审核”目录，给我可打开链接。

脚本参考：`python3 workflow.py source --help`、`python3 workflow.py review --help`、`python3 workflow.py review-html --help`。先配置 [Google回译与Gemini](references/translation-provider-status.md)，分别使用本人密钥；真实调用需要授权。不能把关键词命中当作语义完全匹配，跨段重组先审，回译不自动覆盖定稿。

## 4. 字幕预检与 HeyGen

作用：按本人确认的语速准备目标字幕，核对文案和画面时长，上传到本人 HeyGen 校对制作。

> 用我批准的文案和视频，按目标语言确认的语速准备字幕并预检。核对我的HeyGen账号、Proofread模式、时长和费用，经我确认后创建草稿，给我网页校对入口；我试听确认后，再单独确认生成与下载。

安装：`sh ./install.sh heygen`。本人运行 `./.tools/bin/heygen auth login --oauth` 并核对账号。脚本参考：`python3 workflow.py speech --help`、`python3 workflow.py heygen-web --help`，详细参数及授权见 [INTEGRATIONS.md](INTEGRATIONS.md)。语速可以本人提供、确认语言平均值估算或从听审样本测算；预估字幕不等于实际音频字幕。创建与生成分别授权，不自动扣费。

## 5. 实际音频对齐、包装及发布资料

作用：下载后按真实音频对齐并听审，使用包内字幕模板，生成标题简介和标签。也可继续用自己的剪辑软件。

> 按实际成片音频对齐审定文案，保留文字，标出疑点让我听审。再使用包内字幕模板包装，未指定模板时先评估画面，失败报错；给我成片及标题简介审核，不上传。

按需安装：`sh ./install.sh align`、`sh ./install.sh packaging`。入口参考：`python3 workflow.py align --help`、`python3 workflow.py captions --help`、`python3 workflow.py post-heygen-qc --help`、`python3 workflow.py metadata --help`。`package`保留为基础剪辑入口，不作为默认字幕模板。首次自动对齐可能下载模型；听审和成片验收仍由本人完成。

## 6. YouTube 私密上传

作用：将本人批准的成片和发布资料上传到指定频道，保持私密并检查处理结果。

> 核对我授权的YouTube频道，用我确认的最终成片、封面、标题和简介做私密上传。完成后给我视频链接和处理结果，不公开发布。

安装：`sh ./install.sh youtube`；按 [集成说明](INTEGRATIONS.md) 配置自己的 Desktop OAuth JSON、频道与账号。入口：`python3 workflow.py youtube --help`。此授权不涵盖公开发布；状态不明时查原任务，不盲目重复上传。

## 7. 保存与升级

所有任务输出独立保存；需要统一移交清单才使用 `python3 workflow.py delivery --help`。审核、批准与实际质检记录即使不用清单也要保留。

审核使用本地 HTML；改稿后打开新链接。开头预览不保证恰好3秒，需检查实际时长与听感。其他使用条件见 [README](README.md#使用时需要注意)。更新与回滚按 [UPGRADE.md](UPGRADE.md)；不要把个人资料或凭据上传回仓库。
