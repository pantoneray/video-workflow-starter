# 同事 Mac 首次安装验收

状态：待同事实际运行。本机/虚拟环境结果不代替另一台Mac，Apple Silicon与Intel分别记录。先用确认交付的候选版本，记录ZIP文件名与SHA，不混用不同候选目录。

1. 将完整 Skill 文件夹解压到自己的 `~/.codex/skills/video-workflow-starter/`（或本人已配置的技能目录），然后再安装依赖；不要拷贝维护者的.venv、账号目录或运行数据。本轮暂不配置 HeyGen/YouTube。
2. 在该目录终端运行 `sh ./check-env`。记录macOS、芯片及Python/FFmpeg/ffprobe检查结果。缺依赖按README补齐，不绕过失败项。
3. 运行 `sh ./install.sh base`。只在包内创建环境；不使用all，不启动生产。不要求先配置Notion或Gemini。
4. 运行 `./.venv/bin/python -m unittest discover -s tests -p 'test_review*.py'`。这些是隔离临时目录/本地HTTP测试，不会上传视频或形成真实批准。若交付包尚不含某新增测试，按该包报告标注缺项。
5. Notion 测试仅适用于实际包含 `tests/test_notion*.py` 的交付版本；没有这些测试时记录“不适用”，不要把 `Ran 0 tests / OK` 当成通过。含有时运行 `./.venv/bin/python -m unittest discover -s tests -p 'test_notion*.py'`，检验缺凭据与模拟权限边界，不会读取本人真实 Notion；通过也不代表真实页面提交或写权限已验收。本地 HTML 审核不依赖 Notion。
6. 可选包装依赖验收另运行 `sh ./install.sh packaging`，再运行对应包的字幕测试；这一步可能下载安装依赖，先看安装输出。真实素材试片、人审和外部账号验收另记，不以单元测试替代。

反馈请包含：候选文件名/SHA、macOS版本、Apple Silicon或Intel、上述命令成功/失败、失败时的脱敏错误（不发API key、环境变量全集、账号授权文件）。不要求同事手写生产JSON。只有回执与本人确认到齐，才把跨机状态改为已验证。安装后基本流程仍需一轮可播放的本人素材/审核页面试用；单独测试通过只算技术安装验收。

验收目标：Mac。跨设备状态：`not_verified`；具体设备与执行回执尚未取得。
