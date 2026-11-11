# 当前 Mac 验收记录（更新于 2026-11-11）

## 2.3.17 模板副本、最新规则与解压使用

- 仓库母版独立拉取，固定为 v1.4 / `2e8c0e06740f5a1e8fa21a7519ece85561bdc79a`。副本包含 55 个上游文件；源码、六套规格、OFL 字体、许可和合成测试齐全。运行与安装不访问母版仓库。
- 当前 Mac 70 项回归测试全部通过。新增测试实际渲染 1080×1920 合成片，核对审定稿大小写及标点、ASS 中轴 x=540、完整解码、源片 SHA256 不变及拒绝覆盖；不以合成词时长证明真实语言音频已对齐。
- 上游完整测试七种组合（A/B/C/D/E 插画/E 实拍/F）全部输出视频和预览，规格与字幕中轴检查通过。另抽取每种三帧查看，合成头部未被字幕遮挡。此项是渲染与字形样本，不替代真人手机预览、听审或口型验收；没有声音的 C/F 合成样本不证明响度达标。
- 本机系统 FFmpeg 缺 libass；已实际安装 packaging 依赖并调用 imageio-ffmpeg 本地二进制完成模板渲染。基础/字幕依赖检查、Skill 结构检查和文档链接检查通过。
- Mac 真实执行 Swift/Vision 两个入口：合成人物无法识别人脸时 frame-check 返回 needs_visual_review；无声且无法确认嘴部时 silent-mouth 返回 review / mouth_unverified；不自动剪尾。本轮未拿私人真人片做新一次口型准确率或安全剪尾验收，保留源工作流已验证算法及当前限制。
- ZIP 解压到全新目录，实际执行 install.sh packaging、check-env --with-captions、pip check、70 项回归测试（1 项因未安装可选 PDF 依赖跳过）和三个新入口帮助，均通过；使用该解压目录的模板、字体、虚拟环境，无母版仓库调用。
- 最终分发通过文件清单、ZIP CRC、逐文件哈希和私人路径检查。没有 .git、虚拟环境、账号、密钥、生产视频或内部运行回执。
- 未进行真实模型调用、HeyGen 付费生成、YouTube 上传或公开发布。原生 Windows/WSL 未实机验证；Apple Vision 两项仅 Mac 可选，其余平台以视觉复核补足。固定构图渲染不代表自动平滑跟随已交付。

复验：`python workflow.py captions --help` 查看入口；安装 packaging 后执行 `python -m unittest discover -s tests -p 'test_*.py' -v`（应使用已安装依赖的虚拟环境 Python）。上游完整模板测试需 Bash、Pillow 和 PATH 中支持 libass 的 FFmpeg：`bash tools/shorts-caption-templates/tests/run_tests.sh`，会在该工具 tests/out 生成合成样本，勿纳入分发。

## 2.3.16 全片扫描、多切片与动作审核

- 67 项回归测试通过，Skill 结构和基础依赖检查通过。新增最终专项 3 项测试通过。
- 实际生成 650 秒合成视频，普通 scan 默认扫描全部，scan-long 分段重叠覆盖全部，覆盖时长按并集计数、候选全局 ID 唯一、续跑复用分段。
- 同源片实际输出 3 条 30–45 秒切片，包含第 10 分钟之后的候选，逐条完整解码通过、源片 SHA256 不变。
- review 实际生成连续预览和待审核模板。七类动作逐项注入过多、频繁、不确定、未审核等标注时全部拒绝生成切片清单；未完整查看也拒绝。动作标注为离线替身，不代表自动人物动作识别能力，实际需连续视觉审核。
- 旧规则保留。低帧率样本暴露末帧附近抽帧失败，预览采样改为距候选端点 1 秒；连续预览仍覆盖整段。
- 原生产系统和底层 slice.py 未修改；当前审阅目录已更新，未重新打包 ZIP。

## 2.3.15 四项核心能力检查

- 当前 Mac 包内环境：64 项离线测试全部通过；基础依赖、HeyGen CLI Proofread/SRT/Precision schema、YouTube/API 备用/包装/PDF 依赖检查通过，pip check 无依赖冲突，Skill 结构与文档本地链接检查通过。
- 干净临时目录：按发布文件清单复制包，实际执行 install.sh youtube（同时完成基础环境及 Pillow 安装），check-env --with-youtube、pip check 通过。64 项测试运行通过，其中 1 项因未安装可选 PDF 依赖跳过；扫描、检索、翻译、HeyGen、YouTube 的统一命令入口均可启动。
- 切片：既有合成视频测试实际执行 FFmpeg 候选筛选、30–45 秒裁切、完整解码及源片不变检查，未修改切片/长片扫描脚本。
- 文案与翻译：新增“Markdown 标题紧接正文”样本，确认正文、章节与行号不丢失。已有术语、独立翻译、盲回译、返修及过期批准拒绝测试保留通过；翻译核心脚本与上版字节一致。本次没有调用真实模型。
- HeyGen：新增同一草稿从旧稿修订为新版并重新获批的样本；只调用模拟 generate，不再次 create，原草稿记录不变；旧批准或远端字幕不一致仍被拒绝。交付检查同时接受绑定原草稿的新获批版本，并拒绝丢失修订关联的记录。平台请求均为离线替身，不产生实际费用。
- YouTube：保留 private 上传、账号/频道、文字回查测试；新增配置相对客户端路径验证，支持从其他工作目录调用。Pillow 实际随 youtube 安装到干净环境。没有真实上传。
- 回归中曾发现路径断言未考虑 macOS /var 与 /private/var 的同一目录映射，已将测试预期规范化后通过；产品代码仍按配置所在目录解析路径。
- 新 ZIP 使用上版显式文件清单，排除虚拟环境、CLI 二进制、运行素材及凭据。另一台 Mac、原生 Windows、WSL 未实机运行；使用者自行安装和授权，平台生成内容仍需实际听审。

维护者复核命令（在包目录）：

```sh
sh ./check-env
.venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v
sh ./check-env --with-heygen-cli --with-youtube
```

Windows 原生用 `.venv\Scripts\python.exe` 运行测试；HeyGen CLI 的检查在 WSL 内执行。安装哪些可选组件，就检查相应组件。

## 2.3.14 HeyGen 交付回执链

- 合成 35 秒原片经本包 FFmpeg 工具制成上传副本，离线构造同一任务的预检、视频资产、草稿、网页试听、Output SRT、生成及下载回执，并与当前获批译稿和最终成片一并登记。CLI OAuth 和 API Proofread 两种回执形态的交付验证通过；把草稿的上传视频哈希换成另一值并同步更新文件清单哈希后，交付验证拒绝。平台回执为模拟，不能证明真实账号、字幕上传、费用或成片听审。

## 2.3.13 包外配置跨目录调用

- 在临时项目写相对 `life_corpus` 与 `output`，从另一工作目录实际运行 `project check` 和 `source_search.py`，均定位到配置所在目录并得到带绝对出处的候选；项目记忆记录同一资料路径。`guide` 的相对路径测试也通过。当前 Mac 包内 61 项离线测试通过。另一台 Mac/Windows 的目录和文件权限行为仍待实机验收。

## 2.3.12 上传副本离线实测

- 用 FFmpeg 合成含画面和音轨的本地 3 秒视频，实际运行 `upload-video` 压至 350000 字节预算内并验证 H.264/AAC、完整解码、时长与源片 SHA256 不变；同路径重跑拒绝。将输出副本接入 `speech prepare` 后，预检哈希确实绑定副本。此测试不证明 HeyGen 接受真实长片或账号权限。当前 CLI 本机帮助写明视频简单上传 50 MB，工具默认保留 2 MB 余量。

## 2.3.11 封面与私密上传任务绑定

- 离线模拟验证：同频道另一视频 ID、成片哈希变化、资料版本变化、账号变化或隐私改 public 时，`set-thumbnail` 在 OAuth 前停止；匹配的私密上传回执哈希写入封面结果，并纳入交付证据链。接口响应不能证明封面在 Studio 实际显示，仍需本人查看。未执行真实上传。

## 2.3.10 网页校对稿与译稿批准绑定

- CLI OAuth 路线的 `prepare-web-review` 与 `generate-reviewed` 现在要求当前 `vN.json`、译稿批准及草稿回执。离线模拟验证：同账号、同 Proofread ID、同语种、同译稿整版哈希、SRT 正文及远端字节均匹配才可到最终生成调用；网页改字后会在付费授权占用及远端生成前停止。模拟的审核人字段不证明真人已试听；本轮未登录或产生真实 HeyGen 费用。

## 2.3.9 本人术语表接入译审

- 离线测试以包外临时 CSV、JSON、Markdown 与 TXT 样本核对语言过滤、当前原文精确命中、冲突译法拒绝、相对配置路径、来源文件 SHA256、返修重新选择术语及旧批准失效；模型提示模拟证明盲回译没有中文原文或术语参考，其他模型提示不含本机术语表路径或哈希。未将真实术语或私人项目文本发给模型。
- 当前 Mac 包内隔离环境 57 项测试与联合可选依赖检查 PASS，Skill 结构检查 PASS。2.3.9 ZIP 共 78 文件；全新临时目录解压后，基础安装、环境检查、57 项离线测试（系统 Python 缺可选 PDF 依赖跳过 1 项）、只读阶段引导和结构检查 PASS。ZIP CRC PASS，白名单扫描未见私人路径或常见凭据标记。跨设备、真实模型译审与真人术语审核仍待验收。

## 2.3.8 选文风险提示

- 离线合成 MD 样本以 `因此` 开头、缺上一段、以冒号结尾并跨到下一章；`source_search.py` 同时列出指代/承接、缺上文、未完句尾、章节边界、深入法义专业复核和关键词仅作候选的 `risk_checks`，保留原文与 `pending_human_review`。这些规则只验证可观察的文本形态，不能替代语义或教义审核。

## 2.3.7 本机实际音频对齐

- 用 macOS 内置 `say` 临时生成英文语音，原文为 `This is a short test. Please listen carefully.`；包内 `workflow.py align` 经 `.venv-align` 和本机已缓存 Whisper base 模型在 CPU 上实跑。音频 2.819625 秒，输出两条 SRT：第一条 0.040–1.090 秒，第二条 1.540–2.560 秒；`text_exact: true`、`issues: []`，无额外锚点。输入音频 SHA256 `225b81796224f7c1af19b0a8a8a2f3fe9bfe32a41c39dca0ded88d94962be287`，文本 SHA256 `78b132c87b998fabf7e120aee503b21d39a41e5abf1ee37f2e575cec85563fbb`。
- 这次是本机实际模型推理与临时合成音频，不是仅靠 mock；临时媒体未随 ZIP 分发。时间结构和文字完整不等于人工听审准确，也不证明真实 HeyGen 成片、其他语种或其他设备可用。

## 2.3.6 只读统一阶段引导

- `workflow.py guide` 已在当前 Mac 用真实本机依赖检查运行 `prepare` 与 `heygen` 阶段：均返回本机环境 PASS，并明确平台账号与付费权限未核验；未登录或提交。离线测试还覆盖配置读取不改写、选文和选片并行、已有交付目录的顺序恢复、HeyGen API Key 覆盖 OAuth 提示。
- Guide 是恢复与操作提示，实际选文语义、真人审稿、账号权限、费用和远端平台结果仍由对应阶段独立验收。

## 2.3.5 交付关键证据链

- 当前 Mac 包内隔离环境 51 项测试、联合可选依赖与 Skill 结构检查 PASS。合成 35 秒视频样本将选文候选、当前译稿及批准、裁切清单、SRT、HeyGen 下载回执、人工听审、包装回执、实际 PNG 封面、发布批准和 YouTube 私密回执纳入交付目录，证据链通过；仅占位文件不能签收。将处理回执改为 public 并同步更新清单哈希后，证据链仍拒绝通过。
- 复制 JSON 中的 Mac/Windows 绝对路径会在清单中标注为可能需要原素材的本机依赖。样本中的审核与平台回执是离线构造，不能当作真人审稿、真实上传或新设备运行证明。

## 2.3.4 交付清单与人工签收分离

- 包内隔离环境 49 项测试及联合可选依赖检查 PASS，Skill 结构检查 PASS。测试证明十类文件齐全时只返回 `artifact_inventory_complete`；未签收不得报告 `handoff_complete`，漏项不得签收，签收后新增或修改文件使签收失效。
- 人工签收字段只是审核人的明确记录，程序不能证明实际播放、专业内容准确或 YouTube Studio 显示。本轮未执行任何真实平台上传、付费或跨设备验收。

## 2.3.3 YouTube 处理状态回执

- 当前 Mac 离线模拟验证私密上传后保存 `upload-verified.json`，处理等待结果可保存到新回执文件；重复路径会在 OAuth 与远端请求前拒绝。没有上传真实视频，远端处理和封面回显仍待本人账号验收。

## 2.3.2 逐任务费用授权关口

- 当前 Mac 包内隔离环境运行 47 项测试全部通过，联合 HeyGen CLI、YouTube、包装、PDF 和对齐依赖检查 PASS；Skill 结构检查 PASS。新测试核对待填回执拒绝、账号/计费类型/模式/时长/配置变化拒绝、一次性授权占用，以及最终生成 Proofread ID 和 SRT 绑定。CLI OAuth 路线测试仅模拟远端调用；API Key 付费命令在调用前增加相同回执校验。
- 费用估计和预期上限由实际使用者从本人账号填写。脚本只核对批准范围，无法限制 HeyGen 实际扣费，也没有代替本人授权。本轮未发起真实付费任务、外部上传或跨设备安装。
- 最终 2.3.2 ZIP 仅含白名单文件，CRC PASS；扫描未发现个人路径或常见密钥标记。全新临时目录解压后，按说明以 Python 3.12 运行 `sh ./install.sh base`、`sh ./check-env`、47 项离线测试与 Skill 结构检查均 PASS（系统 Python 缺一项可选 PDF 依赖，跳过 1 项）。

## 2.3.1 全新目录安装验证

- 2.3.0 ZIP 经 Python 解压到全新目录后，`sh ./install.sh base` 首次实跑因 `./check-env` 无可执行权限失败。2.3.1 修复安装脚本内部调用和说明命令；使用 Python 解压新 ZIP（脚本实际失去执行权限），以本机 Python 3.12 执行 `sh ./install.sh base` PASS、`sh ./check-env` PASS、45 项离线测试通过（3 项可选依赖测试跳过）、Skill 结构检查 PASS。这证明本机干净目录的基础安装，不证明另一台 Mac/Windows。

## 2.3.0 发布审核与包装音轨

- 包装合成视频测试覆盖字幕烧制、片头片尾/淡入淡出/配乐、完整解码、源文件保留，并比较配乐音量设为零时原声包装前后的平均音量。正音量配乐仍需人工听审响度和可懂度。
- 新增实际合成成片与 PNG 封面的人审回执测试：当前译稿、标题简介 tags、封面和最终视频哈希一并绑定；候选或封面/成片变化会使旧批准失效。YouTube 模拟上传回读额外核对标题、简介和 tags；未批准候选在 OAuth 前被拒绝，CLI 取用审核稿参数。统一入口的包内虚拟环境选择有独立测试。当前 Mac 包内隔离环境 45 项测试通过，真实账号与成片听审仍待验收。

## 2.2.4 CLI 契约检查

- 当前 Mac 包内官方 HeyGen CLI v0.11.0 的本地 `--help`、`--request-schema` 和 `--response-schema` 与脚本调用字段一致；`./check-env --with-heygen` PASS。用虚构 `HEYGEN_API_KEY` 测试时按预期 FAIL，说明 OAuth 覆盖风险会在预检中显现。未创建新 HeyGen 资产或付费任务；schema 存在不能证明目标账号有权限或动态时长的实际效果。

## 2.2.3 阶段包

- 译审离线测试核对四个独立阶段及提示隔离：独立翻译只见中文原文，盲回译只见目标语，对照复核再见两版译文；缺独立译文不能获生产批准。审稿包显示独立译文。当前 Mac 41 项离线测试通过；真实模型、目标语种和人工审稿身份未在本包新任务中验收。

## 2.2.2 阶段包

- 选文检索新增重复出处、跨章节邻近段落、空主题范围与不可读编码的离线测试；包内隔离环境 41 项测试通过。关键词命中和自动提示仍不能证明真实语义、专业准确性或摘录完整性。

## 2.2.1 阶段包

- API Key 备用路线的付费 Proofread 创建、字幕更新和最终生成已加当前译稿整版批准关口；修改原文后旧批准在生成前失效。写入前核对预期邮箱，错账号在提交前中止。交付核验报告缺失阶段，不将部分文件判成完整交接。当前 Mac 包内隔离环境 40 项离线测试通过、可选依赖检查 PASS；全新解压后基础环境与结构检查通过，系统 Python 的 40 项测试通过且 1 项可选 PDF 测试因缺少 pypdf 跳过。真实 API Key、网页编辑器、付费生成和跨设备仍未验收。

## 2.2.0 阶段包

- 当前 Mac 的包内隔离环境：39 项测试通过；基础、YouTube、PDF、包装、音频对齐依赖检查均 PASS；Skill 结构检查 PASS。测试增加整版哈希批准、HeyGen 草稿/目标 SRT/网页人审关口、Google 邮箱/GCP 项目/频道分开拒绝、YouTube 只读有限重试、模型结果未知不自动重发，以及成片字幕速度报告/人工回执输入哈希。上述平台测试均为 mock，未触发真实 OAuth、付费或上传。
- `source_search.py` 现在保留邻近段落线索并明确语义与断章仍需人审；长片续跑改变分段参数时拒绝复用旧目录。相关离线测试通过。
- 当前系统没有 PowerShell、Windows 虚拟机或另一台 Mac；Windows 原生、WSL 和其他账号仍未实机验收。新 YouTube `openid email` OAuth 范围与 HeyGen 网页人审记录尚未真实账号验证；这些不以离线测试代替。

## 2.1.0 阶段包

- `./install.sh packaging` 在包内隔离 `.venv` 安装 Pillow 11.3.0 后，`./check-env --with-packaging` PASS；系统 Python 3.9 未装 Pillow 时该可选检查按预期 FAIL，基础检查仍 PASS。
- `.venv/bin/python -m unittest discover -s tests -v`：最终 34 项通过。新增临时项目路径失联/记忆续写、自定义主题与出处、扫描 PDF 的 OCR 提示、三次独立译审调用及盲回译、旧批准失效、长片分段续跑覆盖、合成视频字幕烧制/片头片尾/配乐/解码/源片不变、发布资料候选、任务交付哈希和 YouTube 处理后封面模拟；另复制 MIT 对齐工具原有 10 项离线结构测试。
- 本轮只有合成视频和 mock 模型/平台调用；没有向 Gemini 发送私人资料、没有新 HeyGen 付费草稿/生成、没有 YouTube 真实上传。Windows/WSL、新账号、真实语速、实际成片包装和封面显示未验收。
- 本版本已具本地对齐脚本和多条审稿包，但 Whisper 模型权重未下载，未用新包真实音频验收；真实跨设备安装与完整平台运行仍待。详见 `PROGRESS.md`。
- 在当前 Apple Silicon Mac 上用 Python 3.12 运行 `install.sh align`。首次安装后 `stable-ts` 的未固定依赖解析为 torchaudio 2.11.0，与 torch 2.8.0 导入冲突；包内按平台将 torchaudio 固定为与 torch 同版后重新安装，`./check-env --with-align --with-packaging` PASS，实际导入显示 torch/torchaudio 2.8.0、NumPy 1.26.4。尚未下载 Whisper 模型或在实际音频上运行对齐。
- 本机 `install.sh youtube` 与 `install.sh corpus-pdf` 成功；`./check-env --with-youtube --with-packaging --with-corpus-pdf --with-align` PASS。无 OAuth 授权或真实上传。
- 生成 ZIP 后在新的临时目录解压，执行 `python3 workflow.py env` 与 `python3 -m unittest discover -s tests -q`：环境 PASS，34 项运行、其中可选 pypdf 样本 1 项因干净系统 Python 未装依赖而跳过，其余通过。首次 ZIP 漏装 `.srt` 样本使解压测试失败，已加入样本并重打包；最终校验以实际发布物为准。

## 2.0.0

- 官方 HeyGen CLI v0.11.0 经其安装器下载并校验到包内 `.tools/bin`；`--version` 和 Proofread 子命令帮助核对通过。当前 CLI OAuth `auth status` 只读返回 OAuth、订阅类型，；既有任务状态曾经只读核对。没有创建新资产、草稿或最终生成。
- 网页人工审核的证据来自此前项目中的一条 CLI OAuth Proofread 草稿：有可打开网页链接、Output SRT 回读与版本记录；本便携脚本的新建草稿尚未真实运行，网页可见性须在每个新账号首次使用时核验。
- 脚本的 OAuth 账号不符、API Key 覆盖、视频哈希预检、目标 SRT 文案绑定、草稿只创建不生成、远端字幕不一致时拒绝最终生成均有离线模拟测试；共 14 项测试通过。Windows WSL 安装、其他同事账号及实际速度调节结果尚未跨设备验收。

## 1.3.5

- HeyGen 官方 Proofread 创建、编辑 SRT 上传、最终生成三处 API 文档均给出 `x-api-key` 认证；因此本包保留 API Key 直连，不将 CLI OAuth 设为基础依赖。
- Mac/Windows 安装脚本在安装 HeyGen 依赖后提示检查正确账号。`auth-check --expected-email` 读取 `/v3/users/me` 并核对邮箱，不匹配即拒绝；离线模拟含成功和拒绝案例。
- 当前 Mac `./install.sh heygen`、`./check-env --with-heygen`、11 项离线测试、Python 语法和示例 JSON 通过。当前 shell 没有 `HEYGEN_API_KEY`，故真实账号与上传/付费 Proofread 仍未验收；Windows 安装提示也未在实机测试。本轮未上传或扣费。

## 1.3.4

- 源码核对：包内 `create-proofread` 请求 `POST /v3/video-translations/proofreads`，`proofread-update-srt` 上传目标 Output SRT；最终 `generate-proofread` 现在强制检查同一会话回读 SRT 的回执及批准稿逐字节一致。另有需显式选择的直译路径，不经过 Proofread。
- 认证通道是 `HEYGEN_API_KEY` + v3 REST。`auth-check` 为只读账号验证，离线模拟测试通过。Codex HeyGen 插件可只读访问其连接账号，但包内脚本无法使用插件 OAuth；本机 HeyGen CLI 不在 PATH，脚本也不读取 CLI OAuth 文件。
- 本机运行 `./install.sh heygen` 与 `./check-env --with-heygen` 通过，11 项离线测试通过。当前 shell 未设置 `HEYGEN_API_KEY`，`auth-check` 按预期拒绝；真实 API Key 身份、上传权限和 Proofread 跨账号验收仍未完成。本轮未上传资产、创建付费任务或生成成片。

## 1.3.3

- 官方 HeyGen 文档核对 Input SRT 与 Proofread Output SRT 的不同用途；包内不附带任何私人项目的任务回执、字幕或成片。
- 本次只读审计与文档纠正，未重新提交 HeyGen 生成或扣费；便携 API 路径仍只有离线模拟测试。生成后实际语音仍需逐条听审。

## 1.3.2

- 文档澄清能力边界，未修改脚本。Skill 结构、基础环境及 11 项离线测试复核通过；包内能力不包括实际音频自动强制对齐。

## 1.3.1

- 仅澄清安装分层与三步入口的范围，脚本行为不变。Skill 结构、基础环境与解压包内离线测试复核；跨设备和真实平台调用范围仍同 1.3.0。

## 1.3.0

- 纠正自然语言入口：不再要求用户给起止时间码；Agent 使用规则配置、FFmpeg 候选扫描和预览帧，自主选出 30–45 秒切点，随后复用切片及质检脚本。
- 合成动态视频的完整离线链路通过：扫描候选、五帧预览、未声明视觉检查时拒绝生成切点、生成切点、重编码切片、完整解码与原片字节不变。合成 20 秒处硬切且后段冻结的视频被检出，未产生跨切点的 30 秒候选。
- 初期人工播放检查仍是验收环节。FFmpeg 阈值及五张预览不能证明所有真实视频都没有细微跳切、卡顿或起止动作突兀；目标 Mac/Windows 的真实素材需抽检并调规则。

## 1.2.0

- 两份交接 ZIP 只读审计；仅复制第二份的标准库字幕工具、虚构样本和三项测试到独立输出目录。源 ZIP 和生产 Skill/脚本未修改。
- `python3 -m unittest discover -s tests -v`：8 项通过，覆盖语速候选校准、已批准 profile 的字幕预估、时长不匹配阻断、SRT 结构与原文检查、切片/解码/源文件保留、HeyGen 校对与动态时长参数的模拟 API 路径、YouTube 私密上传模拟路径。
- HeyGen 真实 API 权限、目标文案控制、Proofread 收费行为、动态时长的实际生成效果和 Windows 实机仍未验证。生成后的字幕必须按实际音频另行对齐与听审。
- 当前 Mac 的系统 Python 3.9 创建虚拟环境时卡在 `ensurepip`，手动中止；改用本机 Python 3.12 建立隔离测试环境，安装可选 HeyGen/YouTube 依赖成功，`scripts/check_env.py --with-heygen --with-youtube` 通过。安装脚本支持 `PYTHON_BIN` 指定解释器；该环境不随 ZIP 分发。

## 1.1.0

- `./install.sh base` 与 `./install.sh all` 均成功；全新 Python 3.9 虚拟环境安装 HeyGen/YouTube 可选依赖成功，`./check-env --with-heygen --with-youtube` 通过。
- `python3 -m unittest discover -s tests -v`：3 项通过。新增测试使用模拟接口验证 HeyGen 资产上传、翻译提交、完成任务下载与防重复回执；YouTube 测试验证频道校验调用、强制 `private`、上传意图与回查回执。
- 未使用真实 API Key、OAuth 令牌或付费额度；未对真实 HeyGen/YouTube 发请求。Windows PowerShell 安装和系统凭据存储尚未在 Windows 实机运行。

## 1.0.0

- 结构：要求的 Skill、说明、配置、脚本、测试和变更记录齐全；示例 JSON 可解析。
- 依赖：Python 3.9.6、FFmpeg、FFprobe、libx264、AAC 检查通过；无 Python 第三方库要求。
- 样本：`python3 -m unittest discover -s tests -v`，1 项通过。临时合成视频切片后，manifest 哈希与文件一致，完整解码 PASS，时长在预期范围；源片大小、mtime、SHA256 不变；同目录重跑被拒绝。
- 未在另一台 Mac、Premiere Bridge、Notion 或 HeyGen 环境实测；这些不影响离线基础功能。

## 2.3.19 字幕字号与说明

六套模板七种组合完整合成渲染测试通过；每种查看三个时刻，示例字幕居中且未遮挡合成人物面部。新字号同步到 JSON、生成脚本和 18 份 ASS 样式头；标题与姓名条字号保留。中、拉丁和西里尔示例可见正常字形。合成示例不替代具体人物、长句及手机端逐条检查。新版说明完整覆盖安装、配置、六种日常步骤、审核目录及手动更新；未声称自动更新脚本已实现。

## 2.3.20

A/C/D/E 各增加 8 字号；B/F 字节比对未变，其余模板配置除 size 字段外一致。完整七种组合渲染测试通过，21 张样本帧检查字幕居中、未遮挡合成人物面部。具体语言长句仍需逐条检查。
