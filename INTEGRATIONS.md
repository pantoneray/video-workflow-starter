# 平台集成说明

四项核心能力可按用户提示词分步执行。以下命令主要供 Codex 调用；使用者负责登录、实际审核和明确授权，Agent 可如实记录用户回复及其来源，不要求用户手写技术 JSON，也不得把未表达的意见记为通过。


离线切片、语速预检、字幕结构检查和成片技术质检均不依赖平台。HeyGen **网页人工审核**默认走官方 CLI OAuth；独立 API Key 脚本保留为程序化 SRT 路线，未验收其草稿在网页编辑器中的可见性。凭据和个人配置留在各自设备。推荐统一用 `python3 workflow.py <阶段>` 启动；它会为 API Key、YouTube、包装和封面阶段选择包内虚拟环境。网页 CLI 路线只需标准库。

## 安装

Mac：`sh ./install.sh heygen` 在包内 `.tools/bin` 安装经官方校验和验证的 HeyGen CLI；`sh ./install.sh youtube` 安装 YouTube API 依赖；私密上传前另运行 `sh ./install.sh packaging` 检查封面。Windows 的基础处理可原生运行，HeyGen CLI 需在 **WSL** 终端进入本包目录运行 `bash ./install.sh heygen`；PowerShell 的 `install.ps1 heygen` 会提示这一步。API Key 旧路线另用 `sh ./install.sh heygen-api` 或 PowerShell `install.ps1 heygen-api`。`sh ./check-env --with-heygen` 检查 CLI 二进制、Proofread/SRT/Precision/动态时长命令 schema 和 `HEYGEN_API_KEY` 覆盖风险；**不会验证登录、网页可见性或付费权限**。基础功能无需安装平台工具。

## 每次付费提交的授权记录

创建草稿、最终生成和 API Key 直译是不同操作，须分别由本人确认。先用统一入口生成待确认的本地记录；使用者明确确认后，Agent 可根据真实回复填写人审字段并标明来源，不能自行批准：

```bash
python3 workflow.py paid-authorization prepare-create --operation cli_oauth_proofread_create --expected-email <本人邮箱> --preflight <预检目录>/preflight.json --payload <个人proofread.json> --out <新目录>/paid-create.json
python3 workflow.py paid-authorization prepare-generate --operation cli_oauth_proofread_generate --expected-email <本人邮箱> --draft-receipt <回执目录>/draft.json.result.json --approved-srt <批准的reviewed.srt> --proofread-id <ID> --out <新目录>/paid-generate.json
```

API Key 备用路线把 `--operation` 改为 `api_key_proofread_create` 或 `api_key_proofread_generate`，`--draft-receipt` 指向 `proofread.json.result.json`；直译只运行 `prepare-create --operation api_key_direct_translation`。使用者核对授权账号实际 `billing_type`、当前模式和语种、预检片长、费用估计及来源后，填写 `billing_type`、`estimated_credits`、`max_expected_credits`、`pricing_source`、`reviewer`、带时区的 `approved_at`、`decision: "approve"`，并把三个确认布尔字段设为 `true`。模板不代替本人实际批准。每个提交命令都要传 `--paid-authorization <本次人工批准.json> --confirm-paid`。脚本在远端提交前比对授权范围并为授权文件建立一次性 `.claimed.json` 标记；相同授权不能再次提交。费用上限只是使用者认可的**预期**，不是 HeyGen 端的自动限额，实际扣费需以账号页面为准。旧回执不能用于新视频、字幕、语种或账号。网络结果未知时先查原任务，不重复提交。

## 默认：CLI OAuth → HeyGen 网页 Review & Edit

1. 在有交互终端的 Mac/WSL 中运行 `./.tools/bin/heygen auth login --oauth`，由使用者亲自在官方授权页选择正确的 HeyGen 账号。先取消当前终端的 `HEYGEN_API_KEY`，否则 CLI 会优先使用 API Key；不要共享 `~/.heygen/credentials`。运行 `python scripts/heygen_web.py auth-check --expected-email <本人HeyGen邮箱>`，须看到 `credential_type: oauth` 和 `expected_account_verified: true`。OAuth 走订阅额度，API Key 走独立 API 额度。[官方认证说明](https://github.com/heygen-com/heygen-cli#authenticate)。
2. **上传任何 HeyGen 素材前**，确认源片可使用、人物声像有授权。本机已安装 CLI 的 `asset create --help` 写明视频简单上传上限 **50 MB**；运行 `python3 workflow.py upload-video --source <已切片.mp4> --out <新目录>/upload.mp4` 制作默认不超过 48 MB 的独立 H.264/AAC 副本，可显式传 `--max-height 1080` 缩小画面。脚本检查完整解码、时长、音轨、大小及源片哈希；输出仅表示本地准备完成。**先制副本，再按下节任选一种方式确定用户认可的参考语速，运行 `speech_plan.py prepare` 检查逐句文案、匹配视频时长与预估字幕**。让语种负责人检查断句、文字和预估节奏，将目标 SRT 保存为独立批准稿；预计时间轴仍须在网页按实际试听调整。后续预检、上传、费用授权都使用此副本。不得压缩覆盖原片。
3. 上传通过预检的视频：`python scripts/heygen_web.py upload-asset --file <视频.mp4> --preflight <预检目录>/preflight.json --expected-email <本人邮箱> --receipt <新回执目录>/video-asset.json`。把结果 `asset_id` 填入 [Proofread 配置示例](config/heygen-proofread.example.json)，设单个目标语种、`mode` 与明确的 `enable_video_stretching` 值。动态时长可伸缩片段，但不保证精确语速。
4. 先完成包内逐句/语义段译审，保留当前 `vN.json` 和实际审核人的 `decision.json`。`create-draft` 现在要求 `--text <预检逐句文案.txt> --review-version <vN.json> --review-decision <decision.json>`，脚本核对人工通过、整版哈希、目标语种、文字与语速预检。该任务的费用与授权确认后创建**草稿**：`python scripts/heygen_web.py create-draft --payload <个人proofread.json> --preflight <预检目录>/preflight.json --asset-receipt <回执目录>/video-asset.json.result.json --text <逐句文案.txt> --review-version <vN.json> --review-decision <decision.json> --expected-email <本人邮箱> --receipt <回执目录>/draft.json --paid-authorization <本次人工批准.json> --confirm-paid`。返回 `proofread_id` 和 `review_url_candidate`；链接本身不是网页交接成功的证据。
5. 上传已批准的目标稿时，`upload-target-srt` 同样传 `--review-version <vN.json> --review-decision <decision.json>`；其余 `--file <批准目标稿.srt> --text <逐句文案.txt> --preflight <预检目录>/preflight.json --expected-email <本人邮箱> --receipt <回执目录>/target-asset.json` 参数照旧。脚本核对 SRT 正文、批准译稿与预检文案一致。再运行 `update-target-srt`，只有 `roundtrip_exact: true` 才表示目标 SRT 已按字节回读；回读不同则先取回当前 SRT，重新合理断句并审核，使用**新回执**提交。随后由使用者用同一账号打开网页草稿，确认进入可编辑的 Review & Edit。
6. 使用者在网页 Preview 试听，逐段调整文字、时间戳、声音和停顿；更改文字或时间戳后刷新该段语音。HeyGen 文档没有承诺可直接设置精确的“有效字符/分钟”数值；以本地目标语速作参考，并按实际试听核对自然度。网页编辑完成后运行 `python scripts/heygen_web.py download-srt --proofread-id <ID> --expected-email <本人邮箱> --out <新目录>/reviewed.srt`，检查回读文案、断句与时间轴；若网页只调整停顿和时间戳且正文仍等于当前获批译稿，可进入下一步。若网页改了正文，先返修译审并重新批准，刷新同一视频的语速预检，再取回当前 Output SRT 并重新准备网页审核记录；继续使用原 Proofread ID，不重建草稿。旧译稿批准不沿用，最终生成授权绑定当前 SRT。
7. 先运行 `prepare-web-review --proofread-id <ID> --expected-email <本人邮箱> --approved-srt <reviewed.srt> --review-version <vN.json> --review-decision <decision.json> --draft-receipt <回执目录>/draft.json.result.json --out <新目录>/web-review.json`，脚本生成待确认记录；**实际审核人**在网页打开、逐段试听后明确确认并记录 `reviewer`、`web_editor_opened: true`、`audio_listened: true`、`decision: "approve"`。Agent 可依据使用者明确回复填写记录，不得自行作出人审结论。若使用者已在网页点击 Generate Result，不再调用脚本生成。若明确授权 Agent 代为最终生成，运行 `python scripts/heygen_web.py generate-reviewed --proofread-id <ID> --expected-email <本人邮箱> --approved-srt <批准的reviewed.srt> --web-review-receipt <人工填写的web-review.json> --draft-receipt <回执目录>/draft.json.result.json --review-version <vN.json> --review-decision <decision.json> --receipt <新回执目录>/generate.json --paid-authorization <本次人工批准.json> --confirm-paid`；脚本会核对同账号、同任务、同 SRT 的人工记录、当前整版译稿批准及字幕正文，重新下载远端 Output SRT 并逐字节比对，不一致即停。随后用 `video-status` 查询、`download-video` 下载，运行 `check_output.py`，按实际成片音频重新对齐字幕并听审。

`update-target-srt` 也必须传 `--review-version <vN.json> --review-decision <decision.json>`；若上传后译稿版本发生变化，须重新审定并上传新 SRT。`web-review.json` 还需由审核人填写带时区的 `reviewed_at`（例如 `2026-11-10T10:00:00+08:00`）；缺失或无时区时脚本拒绝最终生成。

网页 Proofread 可修改文本、声音和时间安排，具体操作见 [HeyGen 官方说明](https://help.heygen.com/en/articles/10024431-how-to-use-proofreading-for-video-translation)。此前已有 CLI OAuth 草稿进入网页编辑器的真实回执；使用者在自己的账号首次配置时核对身份和网页可用性；这不要求包维护者逐台代装。Agent 不通过浏览器点击操作 HeyGen。

## 通用语速预检与 API Key 备用路线

**API Key 备用路线：**以下 `heygen_portable.py` 直接调用 HeyGen v3 API，使用本机 `HEYGEN_API_KEY`（`x-api-key`），与上述 CLI OAuth 路线相互独立。官方 API 支持 Proofread 创建、SRT 更新及生成，但这个脚本的草稿是否能在 HeyGen 网页编辑器打开尚未真实验收，因此**需要网页人工审核的任务不要选择此路线**。首次使用先运行 `python scripts/heygen_portable.py auth-check --expected-email <本人HeyGen邮箱>`；通过仍不代表上传权限、额度或网页编辑已验证。插件/MCP 的账号检查也不能代替这条 API Key 的验证。

1. 参考语速任选一种来源：用户提供有效字符/分钟；Codex 查找目标语种及相近口播场景的平均语速并换算；或音频样本测算。前两种由 Codex 直接建立 `speed-profile.json`，包含 `locale`、`counting_rule: "unicode_alphanumeric_excluding_spaces_and_punctuation"`、`target_effective_cpm`、`pause_seconds_between_cues`、`max_duration_difference_seconds`、`max_cue_rate_deviation_ratio`；另用 `rate_source` 和 `rate_basis` 记录用户提供或资料来源及换算依据，平均值标为估算，用户确认后设 `approved: true`。不要把词/分钟、音节/分钟直接作为字符/分钟；缺可靠换算依据时改用用户值或样本。无需音频或样本哈希。若选择样本方式，执行 `python scripts/speech_plan.py calibrate --text <样本文案.txt> --audio <样本音频.wav> --speech-seconds <实际讲话秒数> --locale <语言代码> --out <新目录>/speed-profile.json`，再确认参考值、停顿和容差。计数不含空格、标点，不内置跨语种常数。
2. 将定稿文案按自然句逐行保存。执行 `python scripts/speech_plan.py prepare --text <逐句文案.txt> --clip <匹配视频.mp4> --profile <批准的profile.json> --out <新目录>/preflight`。查看 `preflight.json` 的状态及预计时长差，并逐句检查 `planned-not-final.srt`。时长不合就改文案或选片。脚本不判断画面语义是否匹配，须人工观看。预估 SRT 不代表生成后实际音频轴；若要控制目标语言朗读，须在 Proofread 会话中上传经审定的 **Output SRT**。
3. 每人自行设置 `HEYGEN_API_KEY` 环境变量。上传预检绑定的视频：`python scripts/heygen_portable.py upload-asset --file <匹配视频.mp4> --preflight <预检目录>/preflight.json --receipt <回执目录>/video-asset.json --expected-email <本人邮箱>`。复制 `video-asset.json.result.json` 中的 `asset_id` 到 [校对配置示例](config/heygen-proofread.example.json)，填写目标语种代码及标题，并保持 `enable_video_stretching: true`。

   若另有准确的**源语言转录** SRT，可用同一 `upload-asset --file <源语.srt> --receipt <新回执> --expected-email <本人邮箱>` 上传，在创建配置中加入 `"srt": {"type": "asset_id", "asset_id": "该SRT资产ID"}`。这是初始 Input SRT，只辅助源语识别/翻译；不要把目标语言定稿误放到这里。
4. 核对任务、额度并获得本次授权后创建校对会话：`python scripts/heygen_portable.py create-proofread --payload <个人proofread.json> --preflight <预检目录>/preflight.json --asset-receipt <回执目录>/video-asset.json.result.json --receipt <回执目录>/proofread.json --text <审定文案.txt> --review-version <vN.json> --review-decision <decision.json> --expected-email <本人邮箱> --paid-authorization <本次人工批准.json> --confirm-paid`。用返回的 `proofread_id` 执行 `proofread-status --proofread-id <ID>` 与 `proofread-srt --proofread-id <ID> --out <新目录>/review.srt`。
5. 人工校对翻译、断句和语速，保存**目标语言 Output SRT**。若有双语轨，可用 `subtitle_tools.py validate-pair` 检查时间码与原文完整性，仍需听审。上传已批准 Output SRT：`python scripts/heygen_portable.py upload-asset --file <已批准.srt> --receipt <回执目录>/srt-asset.json --expected-email <本人邮箱>`；再执行 `proofread-update-srt --proofread-id <ID> --approved-srt <已批准.srt> --srt-asset-receipt <回执目录>/srt-asset.json.result.json --receipt <回执目录>/srt-update.json --text <审定文案.txt> --preflight <预检目录>/preflight.json --review-version <vN.json> --review-decision <decision.json> --expected-email <本人邮箱>`。更新后再次用 `proofread-srt --proofread-id <ID> --out <新目录>/roundtrip.srt` 取回并与已批准稿逐字比对，确认 HeyGen 接收的是该版本，再进入最终生成。
6. 最终生成前再次核对视频、字幕和额度，并获得本次授权：`python scripts/heygen_portable.py generate-proofread --proofread-id <ID> --approved-srt <已批准.srt> --update-receipt <回执目录>/srt-update.json.result.json --roundtrip-srt <新目录>/roundtrip.srt --draft-receipt <回执目录>/proofread.json.result.json --receipt <回执目录>/generate.json --text <审定文案.txt> --preflight <预检目录>/preflight.json --review-version <vN.json> --review-decision <decision.json> --expected-email <本人邮箱> --paid-authorization <本次人工批准.json> --confirm-paid`。脚本要求回读文件及其回执绑定同一 Proofread ID，且与批准稿逐字节一致；不一致则拒绝生成。生成后的任务 ID 用 `status`、`download` 查询和下载；运行 `check_output.py`。实际音频与字幕轴可用本包可选的 `align` 工具本地对齐，结果仍须听审。动态时长允许伸缩，不保证语速自然。

**直译路径：**[直译配置示例](config/heygen-translation.example.json) 显式设置 `enable_dynamic_duration: true`；命令另需 `--direct-no-proofread --paid-authorization <本次人工批准.json> --confirm-paid --preflight ... --asset-receipt ... --expected-email <本人邮箱>`。直译不含译后校对关口。校对与直译是两条路径，不对同一任务同时提交。

**Input 与 Output SRT：**创建视频翻译时的 `srt` 入参可上传 **Input SRT** 作为源语转录参考；HeyGen仍会重新翻译，不能用它锁定目标语言文案。要让指定目标文案参与朗读，须走 Proofread：上传审定的 **Output SRT**，回读校验后再生成。HeyGen 官方说明 Output SRT 会按稿朗读；但本便携 API 脚本尚未在其他账号完成真实端到端验收，每条成片仍须听审。资产上传和付费提交先保存意图回执，若网络结果未知，先查远端，禁止盲目重试。

接口依据：[HeyGen 对 Input/Output SRT 的说明](https://help.heygen.com/en/articles/10029081-how-to-get-started-with-video-translation)、[校对会话](https://developers.heygen.com/reference/create-proofread-session)、[下载校对 SRT](https://developers.heygen.com/reference/download-proofread-srt)、[上传校对 SRT](https://developers.heygen.com/reference/upload-proofread-srt)、[最终生成](https://developers.heygen.com/reference/generate-video-from-proofread)、[直接翻译](https://developers.heygen.com/reference/create-video-translation)。三个 Proofread 写接口的官方示例均使用 `x-api-key`。

## HeyGen 成片检查

三种方式取得的参考语速均保存到 `speed-profile.json`，经用户确认后设置 `max_cue_rate_deviation_ratio`，例如 `0.2` 代表逐句字幕显示速度偏离目标 20% 时提示复核；实际阈值由团队决定。成片下载并按实际音频对齐目标字幕后，运行 `python workflow.py post-heygen-qc prepare --video <成片> --aligned-srt <最终字幕> --target-text <审定逐句文案> --profile <批准profile> --out <新qc.json>`。报告同时检查视频完整解码、音轨、字幕正文和时长，列出异常句。实际审核人播放成片并填写报告里的姓名、带时区时间、声音匹配、口型、音画同步、自然度、起止及异常句处理理由；`python workflow.py post-heygen-qc verify --report <已填写qc.json>` 才能出具人工听审回执。字幕显示速度是代理指标，无法自动证明实际朗读语速或口型准确。

## YouTube

每人用自己的 Google Cloud 项目启用 YouTube Data API，创建 Desktop OAuth 客户端。把 [YouTube 配置示例](config/youtube.example.json) 复制到**包外**，填写客户端 JSON 路径、预期 GCP 项目 ID、Google 账号邮箱和频道 ID；凭据不打包。运行 `python workflow.py youtube auth --config <本人youtube.json>`，再用 `verify --config <本人youtube.json>` 分别核对客户端项目、Google UserInfo 邮箱和 `channels.list(mine=true)` 频道。此版本使用 `openid email` 范围与独立 keyring 命名空间，不静默复用旧授权。

私密上传前先安装 `packaging` 依赖以检查实际封面，完成当前译稿及成片的人审：`python workflow.py publication-review decide --candidate <发布资料候选.json> --version <当前vN.json> --approval <译稿批准.json> --video <最终成片.mp4> --cover <实际封面.png> --reviewer <实际审核人> --decision approve --feedback <具体审核意见> --out <新目录/发布批准.json>`。此命令保存成片和封面哈希，并检查视频可解码且含音轨；审核人须先播放成片、查看封面和逐项核对标题简介 tags。可运行 `publication-review verify` 再确认当前版本。

上传命令为 `python workflow.py youtube upload-private --config <本人youtube.json> --file <最终成片.mp4> --candidate <发布资料候选.json> --publication-decision <发布批准.json> --version <当前vN.json> --approval <译稿批准.json> --out <新回执目录>`。程序先本地核对版本、成片和封面哈希，再使用本人 OAuth；远端强制 `private`，并回读频道、隐私、标题、简介和 tags，将含账号与发布批准哈希的结果保存为 `upload-verified.json`。执行 `wait-processing --config <本人youtube.json> --video-id <ID> --out <新目录/processing.json>` 等待处理并保存回执；超时可用新的回执文件继续查询原视频，不重传。处理成功后运行 `set-thumbnail --config <本人youtube.json> --video-id <ID> --image <已批准封面.png> --upload-receipt <上传目录>/upload-verified.json --candidate <发布资料候选.json> --publication-decision <发布批准.json> --version <当前vN.json> --approval <译稿批准.json> --receipt <新回执.json>`，封面设置前会核对该上传回执与当前获批成片、资料、账号及视频 ID 一致；最后由本人在 Studio 查看实际视频与封面。结果未知先核查原任务，不盲目重传。Shorts 自定义封面是否可用须按实际频道验证；[YouTube 官方接口说明](https://developers.google.com/youtube/data/reference/rest/v3/thumbnails/set) 仅证明接口存在。

Google 账号读取依据 [Google OpenID Connect UserInfo 文档](https://developers.google.com/identity/openid-connect/reference)。邮箱只用于本次显示与比对；频道 ID 仍单独核对。首次 OAuth 需由账号本人在官方授权页完成，本包不会配置或复制任何现有账号凭据。

## 验证范围

本包平台调用通过离线模拟测试。`check-env --with-heygen` 检查 CLI 安装，`check-env --with-heygen-api` 检查备用 API Python 依赖；两者都不检查网页草稿。CLI OAuth 已在项目旧任务中实际创建过可打开的网页 Proofread 草稿，但本便携包尚未用新账号/新设备完整验收；首次使用需逐项核验正确账号、资产上传、草稿网页打开、人工试听和 SRT 回读。API Key 备用脚本仍只有离线模拟测试。Windows WSL 实机尚未验收。
