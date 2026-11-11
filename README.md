# Video Workflow Starter

供 Mac / Windows 的 Codex 用户自行安装的视频工作流 Skill。支持批量切片、本地资料选文与译审、HeyGen 网页校对制作、字幕包装和 YouTube 私密上传。

**先读 [安装使用说明](普通使用说明.md)。** 使用发布 ZIP 时解压整个 video-workflow-starter 文件夹，放入本机技能目录后按需安装依赖。六套字幕模板和字体已随包提供。

公开分发版本：2.3.21。隐私检查见 [PRIVACY.md](PRIVACY.md)，功能验证与平台边界见 [VERIFICATION.md](VERIFICATION.md)。

> 字幕包装已随包提供：安装 `packaging` 后使用 `workflow.py captions`，无需 GitHub 权限或 clone。见[模板使用说明](references/caption-packaging.md)与[制作规则](references/production-rules.md)。默认初译可用 `review create --draft 初译.txt --draft-author Codex` 接入独立模型复核。

# video-workflow-starter

普通使用者先看 [简明安装与使用](普通使用说明.md)。本包交付围绕四项：自主切片、文案提取与翻译、HeyGen 上传制作、YouTube 私密上传。支持用户提示词触发、人工修改和按步骤继续；账号及本机安装由各使用者自行配置。

统一入口：`python3 workflow.py <阶段> --help`。先运行 `python3 workflow.py guide --config <本人项目/video-config.json>` 查看本人路径、当前可并行步骤和本机依赖；已有交付目录时加 `--run <交付目录>`，会提示下一阶段和缺失证据。它只读检查，不登录、上传或付费。安装过可选依赖后，入口会为相应阶段自动使用包内虚拟环境。在 Codex 中说“用 video-workflow-starter 从我的资料按生活主题选文，同时从授权视频中选出 30–45 秒画面，先给我审核候选”，Agent 会按 [SKILL.md](SKILL.md) 调用对应脚本；使用者不需手工拼接每个命令。阶段状态以 [PROGRESS.md](PROGRESS.md) 为准。

供各自 macOS/Windows 与 Codex 使用的视频 Skill。四项核心能力由包内脚本执行，具体检查范围见 [PROGRESS.md](PROGRESS.md)。剪辑软件与内容标准由使用者自定；已有材料可用于对应步骤，不强制重跑上游。

音频强制对齐、包装与交付清单为按需辅助功能；Notion 审批和 Premiere Bridge 不在此包中。

## 按需要执行的步骤

1. 准备有使用权的原典/讲记、术语表和视频素材；按下文安装并配置项目路径。
2. 选主题和目标语言；选文与视频画面筛选可并行进行。
3. 审核原文候选及每版译稿，明确记录通过或返修；校准语速、检查逐句文案和匹配画面时长。
4. 上传前若视频过大，用 `python3 workflow.py upload-video --source <切片> --out <新目录>/upload.mp4` 制作独立副本，并以副本重新做语速预检。随后在本人账号确认模式、时长、计费类型和本条费用估计，按[集成说明](INTEGRATIONS.md#每次付费提交的授权记录)分别确认创建与最终生成的授权，由 Agent 记录后创建 HeyGen Proofread 草稿；网页试听调整后，再决定是否生成。最终生成须再次核对 Output SRT 正文仍等于当前获批译稿；网页改字后重新复核并批准，刷新同一视频的语速预检，继续使用原草稿；不因改字重建草稿。
5. 下载成片，按实际音频对齐字幕；运行 `post-heygen-qc` 标出逐句语速疑点，由实际审核人播放检查口型、音画、自然度和画面。完成包装、封面和发布资料后，审核人对实际成片与封面明确签收。
6. 用本机批准回执核对成片、封面与标题简介 tags；再核对本人 Google 账号、GCP 项目和频道，私密上传，等待处理完成并回查。
7. 需要统一交付清单时，再将各阶段文件纳入交付目录并验证。这不是上述四项核心功能的必经步骤。

## 首次准备与选文

1. 在自己的项目目录准备生活应用资料、深入法义原典/讲记的全集 MD/TXT 或可检索 PDF、中文与目标语言术语表、视频素材；可选准备语速样本、字幕规范和品牌参考。只填自己有权使用的路径。扫描版 PDF 先 OCR 并人工核对页码。术语表可从 [CSV 空白示例](config/glossary.example.csv) 复制到**包外**填写 `source,target,language,note`，也支持相同字段的 JSON 数组、Markdown 表格及 `中文 = 译文` 的 TXT；每人按自己的目标语填写，不随 ZIP 分发实际术语。
2. 将 [config.example.json](config.example.json) 复制到**包外**项目目录的 `video-config.json`，填写 `paths`；可用绝对路径或相对配置文件目录的路径，目录应先存在。术语表、项目检查、选文检索和阶段引导使用同一规则。执行 `python3 workflow.py project check --config /项目/video-config.json`，确认相关路径为 `ready`。执行 `python3 workflow.py project init --config /项目/video-config.json --project-root /项目`，在项目内建立 `VIDEO-WORKFLOW-MEMORY.md` 并更新/建立 `AGENTS.md` 的读取入口；不会覆盖已有记忆文件。路径变化时先修改私密配置，再执行 `python3 workflow.py project sync --config /项目/video-config.json --project-root /项目`，只刷新记忆里的受管路径段，保留其他备注。
   配置后可随时运行 `python3 workflow.py guide --config /项目/video-config.json --run /项目/交付目录`。未建立交付目录时省略 `--run`；只看某阶段时加 `--stage <prepare|source|clips|translation|heygen|finish|youtube|delivery>`。报告的 `environment.ready` 只代表本机工具满足检查，**不代表账号、权限或人工授权已完成**。
3. 将 [主题示例](config/topics.example.json) 复制到项目目录，自行修改主题、读者、深度、资料范围和关键词。执行 `python3 scripts/source_search.py --config /项目/video-config.json --themes /项目/topics.json --theme-id life-compassion --out /项目/runs/run-001/candidates.json`。结果逐条保留原文、出处、邻近段落定位和待审状态；重复出处、无法读取文件，以及候选中的指代、缺上文、未完句尾、跨章节与仅关键词命中的风险会提示。`risk_checks` 是复核清单，不能证明主题吻合或语义完整；人工确认上下文、必要前提及专业准确性。文案选材与视频切片可以同时进行。
4. 译审模型参数参考 [models.example.json](config/models.example.json) 存于项目内，`GEMINI_API_KEY` 只放本机环境。`workflow.py review create` 输入一条经审定的出处 JSON、`--language <目标语>`、`--models <项目模型配置>` 及 `--project-config <本人video-config.json>`，从该配置的 `paths.glossary` 中只选当前原文命中的目标语术语；执行初译、只看原文的独立翻译、盲回译和对照复核四次独立调用，并生成 `v1.json`。盲回译不看原文或术语。按句或语义段分别建立记录，用 `workflow.py review-packet` 汇成逐条审稿包。修改时 `revise` 需上一版审稿记录、逐条回应及同一 `--project-config`，重新选术语并生成 `v2.json`；旧批准不沿用。术语表冲突会停下要求人工解决。实际审核人用 `decide` 明确记录通过、修改、拒绝或暂缓；`verify-approved` 核对当前**整版**哈希与决定。旧版若缺独立译文，须先重做译审才能批准用于生产。各模型步骤在输出旁保存意图与结果，断线后复用已完成步骤；结果未知时先人工核查，确需重发再传 `--retry-unknown`。HeyGen 网页路线在创建草稿和上传目标 SRT 时会再次核对该批准与预检文案。各命令运行 `--help` 查看参数；发给模型前需明确 `--confirm-external`。本包没有在此轮对真实资料发起模型调用。

本地实际音频对齐建议用 Python 3.11/3.12：Mac 可运行 `PYTHON_BIN=/本机/python3.12 sh ./install.sh align`（Windows 为 `install.ps1 align`），首次会下载较大的 Python 依赖及模型；执行 `python3 workflow.py align <HeyGen成片.mp4> <逐字定稿.txt> --language <语种代码> --output <新目录/final-aligned.srt>`。脚本保全文字并标出疑点；当前 Mac 已在合成英文语音上实跑，真实 HeyGen 音频、其他语种和 Windows/其他 Mac 未验，结果仍须人工听审。包装另运行 `sh ./install.sh packaging`，以包外 [包装配置示例](config/packaging.example.json) 填本机字体路径，执行 `python3 workflow.py package --video <HeyGen成片> --reviewed-srt <听审后的最终字幕> --config <包装配置> --out <新目录>`。包装可选视频片头片尾、淡入淡出和低音量配乐；不需要就将路径设为 null。包装拒绝预估字幕冒充最终字幕。`cover.py` 基于授权背景生成基础封面；`publication_assets.py` 只从当前批准译稿拟发布资料。实际审核人播放最终成片、查看封面和标题简介 tags 并明确确认后，可由 Agent 记录该决定并运行 `python3 workflow.py publication-review decide --candidate <候选.json> --version <当前vN.json> --approval <译稿批准.json> --video <最终成片.mp4> --cover <封面.png> --reviewer <审核人> --decision approve --feedback <具体意见> --out <新目录/发布批准.json>`；此回执绑定成片、封面和当前译稿哈希。可检索 PDF 另安装 `corpus-pdf`；扫描版 PDF 需先 OCR。

每条任务先运行 `python3 workflow.py delivery init --task-id <唯一ID> --out <新的交付目录>`。各阶段完成后用 `python3 workflow.py delivery add --run <交付目录> --role <source|translation|clips|subtitles|heygen|packaging|cover|metadata|qc|youtube> --file <产物> --copy` 登记文件；不加 `--copy` 仅登记本机引用。HeyGen 阶段按同一任务登记上传文件及每个结果回执；目标文案 TXT 登记为 `subtitles`，已审 Output SRT 登记为 `heygen`。交付前运行 `python3 workflow.py delivery verify --run <交付目录>`。报告分别显示 `artifact_inventory_complete`（十类文件齐全）、`production_evidence_complete`（关键文件可解析且版本、视频、字幕与回执相互匹配）及 `evidence_issues`（缺什么或哪里不符）。复制的 JSON 若仍包含原电脑绝对路径，会列入 `local_dependencies`；文件本身可移交，重新编辑或追溯原素材仍可能依赖原机。

| 角色 | 完整证据所需的主要文件 |
| --- | --- |
| source / translation | 选文候选 JSON；当前 `vN.json` 与对应人工批准 JSON，出处文字、定位和原文件哈希一致 |
| clips / subtitles | 30–45 秒可解码切片及 `manifest.json`；与批准译文一致的最终 SRT |
| heygen / qc | 上传副本（如有）及制作回执、`preflight.json`、视频资产回执、Proofread 草稿、网页试听回执或 API SRT 更新/回读、审核后 Output SRT、最终生成回执、下载成片及 SHA256 回执；实际听审报告 |
| packaging / cover / metadata | 最终成片与 `package-receipt.json`；实际 PNG/JPEG 封面；发布资料候选与人工批准回执 |
| youtube | `upload-verified.json`、处理成功且仍为 private 的 `processing.json`、封面提交结果回执；三者的视频 ID、频道和文件哈希一致 |

**实际审核人**核对来源、译审、播放成片与字幕、发布资料及 YouTube Studio 私密视频和封面后，运行 `python3 workflow.py delivery attest --run <交付目录> --reviewer <姓名> --notes <具体核对说明> --sources-and-translation-checked --clips-and-video-played --subtitles-and-qc-checked --publication-and-cover-checked --youtube-private-video-and-cover-seen`。此时 `handoff_complete` 才可为真；Agent 不代填人工签收。签收绑定清单哈希，之后新增或修改文件会使其失效。程序仍不能独立证明人工看到的平台画面。不会覆盖原文件。

进入 YouTube 阶段时，将 [配置示例](config/youtube.example.json) 复制到自己的项目目录，填本人 OAuth Desktop JSON 路径、预期 GCP 项目 ID、Google 账号邮箱和频道 ID。`python3 workflow.py youtube auth --config <本人youtube.json>` 由本人授权；以后用 `verify --config <本人youtube.json>` 核对身份。私密上传还要传当前译稿、发布资料候选及人工批准回执；命令见 [集成说明](INTEGRATIONS.md)。具体命令见 [集成说明](INTEGRATIONS.md)。

## 成片语速与人工质检

用户直接提供参考语速、确认按语种平均值估算的语速，或认可音频样本测算值后，在 `speed-profile.json` 中设置 `approved: true`、停顿、时长容差及 `max_cue_rate_deviation_ratio`。该容差由团队自行定，不内置语言常数。HeyGen 成片下载后，先按实际音频对齐目标文案并听审字幕，再运行：

```bash
python3 workflow.py post-heygen-qc prepare --video <成片.mp4> --aligned-srt <最终听审字幕.srt> --target-text <审定文案.txt> --profile <批准语速profile.json> --out <新目录/qc.json>
python3 workflow.py post-heygen-qc verify --report <已由实际审核人填写的qc.json>
```

报告列出按字幕显示时长估算的逐句有效字符/分钟。实际审核人播放成片后填写 `manual_review` 中的姓名、带时区时间、五项检查结果和必要的语速例外理由。显示速度只是听审提示，不能证明实际发音速度。

## macOS 安装

1. 解压 ZIP，先将完整包目录放入 `~/.codex/skills/video-workflow-starter/`（或自定义 Skill 目录），然后安装依赖。安装 Python 3.9+ 和带 `libx264`、AAC 编码器的 FFmpeg；Homebrew 示例：`brew install python ffmpeg`。
2. 在包目录执行 `sh ./install.sh`（或先 `sh ./check-env`）。前期选片、裁切和质检不需要平台工具。需要 HeyGen **网页审核**时执行 `sh ./install.sh heygen`，它把官方 CLI 安装到包内 `.tools/bin`；在交互终端运行 `./.tools/bin/heygen auth login --oauth`，由本人在官方页面授权正确账号，再运行 `.venv/bin/python scripts/heygen_web.py auth-check --expected-email '本人HeyGen邮箱'`。`HEYGEN_API_KEY` 会覆盖 CLI OAuth，网页审核路线需先取消该环境变量。YouTube 私密上传运行 `sh ./install.sh youtube`，已包含检查实际封面所需的 Pillow；API Key 备用路线另用 `sh ./install.sh heygen-api`。如系统自带 Python 的虚拟环境创建失败，可安装 Homebrew Python 并用 `PYTHON_BIN=/你的/python3 sh ./install.sh heygen` 指定解释器。
3. 重启或刷新 Codex 的 Skill 列表。也可直接在包目录用命令运行脚本。请先放置 Skill 再安装；安装后不要搬运 `.venv`，更换目录时在新目录重建环境。
4. 按[首次准备与选文](#首次准备与选文)把个人配置存于包外项目目录；不要把路径、语料或账号配置加入共享 ZIP。

## Windows 安装

1. 解压 ZIP，先将完整文件夹放到 `%USERPROFILE%\.codex\skills\video-workflow-starter`（或自定义目录）；安装 Python 3.9+ 和 FFmpeg/FFprobe，并把两者加入 `PATH`。在 PowerShell 执行 `powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1`（只对这次安装进程生效）。基础功能无需 pip 包；YouTube 私密上传另装 `youtube`，已包含 Pillow。HeyGen 网页审核需 WSL：先在 WSL 内另装 Python、FFmpeg/FFprobe，再进入同一包目录运行 `bash ./install.sh heygen`、`./.tools/bin/heygen auth login --oauth`，用 `python3 scripts/heygen_web.py auth-check --expected-email '本人HeyGen邮箱'` 核对账号。WSL 使用独立 `.venv-wsl` 和 `.venv-align-wsl`，不会覆盖原生 Windows 或 Mac 的虚拟环境。原生 Windows 的 API Key 备用路线可用 `install.ps1 heygen-api`，但网页草稿可编辑性未验收。
2. 刷新 Codex。应先放置文件夹再安装，不搬运已安装的 `.venv`。
3. 在 Codex 中给出视频路径和用途，让 Agent 按下文流程选片；直接运行时用 `py -3 scripts\select_candidates.py scan --input 'C:\素材\video.mp4' --rules config\selection-rules.example.json --out 'C:\输出\run-001\selection'`。Agent 看候选帧后生成切点，再调用 `slice.py` 与 `check_output.py`。

个人凭据和配置留在包外，不打进共享 ZIP。平台配置和命令见 [INTEGRATIONS.md](INTEGRATIONS.md)。

## 自主选片并裁切

在 Codex 中说：“用 video-workflow-starter 按规则从这个视频完整扫描并自主选出多条 30–45 秒的连续画面，放到新目录并检查结果。”提供素材路径和用途即可。Agent 应按 [Skill 流程](SKILL.md) 调用脚本并查看候选预览，自己生成切点。不同团队可从 [通用规则示例](config/selection-rules.example.json) 另存本机规则；其中没有特定人物和素材要求。

```bash
python3 scripts/select_candidates.py scan --input /你的素材/video.mp4 --rules /你的规则.json --out /新的运行目录/selection
# Agent 查看 selection/previews 内的候选画面，选出合格 ID；无合格片段则停止
python3 scripts/select_candidates.py review --candidates /新的运行目录/selection/candidates.json --candidate-id 1 2 --out /新的运行目录/review
# 连续查看预览并据实填写 review/review.json 后选择通过的候选：
python3 scripts/select_candidates.py choose --candidates /新的运行目录/selection/candidates.json --candidate-id 1 2 --review-file /新的运行目录/review/review.json --visual-reviewed --out /新的运行目录/cuts.json
python3 scripts/slice.py --input /你的素材/video.mp4 --cuts /新的运行目录/cuts.json --out /新的运行目录/sliced
python3 scripts/check_output.py --input /新的运行目录/sliced/segments/seg-01-selected.mp4 --out /新的运行目录/qc.json
```

`scan` 默认覆盖全视频、候选数量不限。长片优先运行 `python3 scripts/scan_long.py --input /素材/long.mp4 --rules /规则.json --out /运行目录/long-selection --segment-seconds 600`；600 秒是分段步长，不是总扫描上限，分段有重叠以保留边界附近候选。查看 `coverage.json` 的实际覆盖、全片标记和全局候选 ID，同参数续跑跳过完整分段。`review` 和 `choose` 都可直接读取该报告并传多个 ID。机械检测检查镜头切换、冻结和黑帧；动作审核须连续查看整段，拒绝过多特殊手势与过多/频繁低头。脚本不会自动识别人物手势，只核验审核结论；未看完整、未审核或无法确认的候选不能选择。原有质检保留，初期由用户播放检查输出。

## 已知时间码时

在任意工作目录创建 `cuts.json`：

```json
[{"start": 1, "end": 3, "label": "sample"}]
```

```bash
python3 scripts/slice.py --input /你的素材/video.mp4 --cuts cuts.json --out /你的输出/run-001 --dry-run
python3 scripts/slice.py --input /你的素材/video.mp4 --cuts cuts.json --out /你的输出/run-001
python3 scripts/check_output.py --input /你的输出/run-001/segments/seg-01-sample.mp4 --out /你的输出/run-001/qc.json
```

如用户已有明确时间码，也可直接运行上述 `slice.py`。这是附加入口；自主选片不需要用户提供时间码。

验收：`manifest.json` 有源片路径、切点、输出 SHA256；`qc.json` 的 `decode` 为 `PASS`，时长合理，并有视频轨。请观看片头、片尾及内容，确认切点与画面。脚本拒绝覆盖已有输出。准备 HeyGen 时，先按 [可选集成说明](INTEGRATIONS.md) 校准该语种有效字符/分钟，检查文案、视频时长和预估字幕；生成后需用包外已有工具或人工按实际音频对齐字幕。

## 能力来源与边界

- `scripts/select_candidates.py` 从现有选片流程提取通用的“机械预筛→候选预览→Agent 视觉判断”结构；不复制绑定人物、Gemini、路径和私有阈值的生产脚本。它新增的 FFmpeg 场景/冻结/黑帧检测只生成候选，不宣称自动审美或自然动作判定。
- `scripts/slice.py` 基于项目已跑过的独立 `scripts/slice.py`，保留 FFmpeg 精确切片与 manifest；为跨设备使用补了路径配置、时间码校验和防覆盖。
- `scripts/check_output.py` 复用原成片脚本的 FFprobe、完整解码与 SHA256 检查思路，独立检查任意剪辑软件的导出文件。
- 源项目记录了样片与真实长视频切片、源文件 size/mtime 不变；这些是原环境证据。此包的离线样本测试只证明当前 Mac 的基本功能。另一台 Mac 或 Windows 的编码器、文件权限和实际剪辑软件互操作仍需在该机运行环境检查与样本测试。
- `scripts/subtitle_tools.py` 来自第二份交接包的标准库字幕结构工具，去掉覆盖开关后独立复用；语速预检脚本新增的是必要的最小补充。两份交接包的业务文案、旧项目语速常量和账号规则均未打包。
- 包含去业务化的单条译审与可选本地强制对齐；不包含原项目 Notion 审批、特定 HeyGen/YouTube 账户、人物筛选或私有素材。平台入口按需安装，YouTube 仅支持私密上传。

## 测试

`python3 -m unittest discover -s tests -v`。测试在临时目录生成合成素材，检查候选生成、切点生成、切片、哈希、解码、语速预检、字幕结构、源文件保留及模拟平台接口；不上传或联网。

## 批量、主题和审核的完整用法

见[批量切片与审核说明](references/batch-and-review.md)。文件夹批量任务使用 `batch-clips`，支持总数量、每源片上限、顺序或有限并行；主题先列出供选择，新主题仅在用户确认后保存到项目主题库；审核文件保存到本次任务的 `审核/` 并给出可点击路径；标题简介由 Codex 调用现有 Gemini 脚本生成，用户确认后上传。
