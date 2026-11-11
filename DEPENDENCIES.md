# 依赖与许可清单

| 阶段 | 依赖 | 安装方式与许可核对 |
| --- | --- | --- |
| 基础切片/质检 | Python 3.9+ 标准库、FFmpeg/FFprobe（需 libx264、AAC） | 系统安装；FFmpeg 的具体许可证取决于发行版和编译选项，分发包不含二进制。 |
| 可检索 PDF | pypdf | `requirements-corpus-pdf.txt` 按需安装；安装时查看包元数据与随附许可证。扫描 PDF 的 OCR 工具不在包内。 |
| 字幕包装/封面 | Pillow、imageio-ffmpeg（模板需要 libass） | `requirements-packaging.txt` 按需安装；本机验证 Pillow 11.3.0 元数据为 MIT-CMU。包内附模板的 SIL OFL 字体与合成预览图，不含私人品牌素材。模板优先用系统 FFmpeg，缺少 libass 时选用 imageio-ffmpeg 安装的本机二进制。 |
| 本地音频强制对齐 | `faithful-audio-align`、stable-ts、Whisper、PyTorch、NumPy | 复用现有 MIT 源码，原许可在 `tools/faithful-audio-align/LICENSE`；`install align` 安装到单独 `.venv-align`，首次模型下载，依赖和模型各自许可需核对。实际音频不上传。 |
| HeyGen 网页校对 | 官方 HeyGen CLI | `install.sh heygen` 从官方安装入口另行下载；CLI 不装进 ZIP。按官方发行包的许可证和服务条款使用。 |
| HeyGen API 备用 | requests、requests-toolbelt | `requirements-heygen.txt` 按需安装；本机检到 requests 2.32.5 Apache-2.0、requests-toolbelt 1.0.0 Apache 2.0 元数据。 |
| YouTube 私密上传 | google-api-python-client、google-auth-oauthlib、google-auth-httplib2、httplib2、keyring 等；含发布封面审核所需 Pillow | `requirements-youtube.txt` 已包含上述依赖，包装功能另可用 `requirements-packaging.txt`；目标机器安装后查看各包元数据与许可证。OAuth 客户端及 token 不在 ZIP。 |

本 Skill 内新写的脚本、示例配置和测试由本包维护；`faithful-audio-align` 的 MIT 许可随源码保留。此前交接 ZIP 中复制的 `subtitle_tools.py` 与虚构样本的转发权限需由使用者核对其原许可/提供方授权。新增字幕模板代码及规格采用 MIT、字体采用 SIL OFL；许可证随 tools/shorts-caption-templates 保留。预览和测试素材为合成示例，不是生产素材。本包不附带私人媒体、原文语料或模型权重。上传原文到模型、使用平台额度及分发产物仍由各团队依据自身授权决定。

Mac 可选构图与静音口型检查：Apple Vision、AVFoundation 和 Swift（Xcode Command Line Tools），系统提供，不随 ZIP 分发；Windows 可使用人工视觉检查。模板渲染本身不依赖 Apple Vision。
