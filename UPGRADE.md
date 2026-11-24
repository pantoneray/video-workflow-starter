# 已安装用户升级到 v2.3.22-rc.12

不升级不影响现有使用。升级前备份旧包和个人配置，按需补充以下配置。

## 升级前要补什么

1. **译审**：旧版 Gemini-only 配置可保留；Codex 会引导补配 Google，或询问是否本次临时沿用 Gemini 回译。按 [回译配置](references/translation-provider-status.md) 增加 Google Cloud Translation API 凭据，本机环境变量 `GOOGLE_TRANSLATE_API_KEY`；包外模型JSON设 `backtranslation_provider: "google_translate"`、`backtranslation_model: "nmt"`。原 Gemini 初译/独立校对配置保留，`GEMINI_API_KEY` 单独配置。补配前可继续切片或包装；临时 Gemini 须经本次明确同意并如实标注。
2. **字幕样式**：新版默认自动评估模板，字幕默认上移80像素。要保持旧效果明确指定旧模板并用 `--shift-up 0`，实际画面仍需检查。不要强制覆盖本人明确的模板配置。
3. **历史任务**：保留旧稿、旧批准和旧收据，不自动迁移批准。新审核轮次绑定当前稿件，改稿须重审。
4. **Notion**：不是必装项；本地HTML审核无需Notion。包内 Notion 工具需另行接入，不提供开箱即用的完整审核流程。

## 本次新增知识库

使用新版完整包更新代码后，Codex 执行一次 `python3 workflow.py library setup --config <本人项目/video-config.json>`。默认资料存入该配置同级的 `资料库/suodj/`，不覆盖原有 paths、模型配置、主题或其他知识库。配置变更前保存备份；已有登记只核对并复用。随后 `project sync` 刷新受管路径和规则。

已有 Smart Library 同步副本时，在 setup 指令上加 `--path <已有suodj目录>`；选文期间暂不从另一工具更新同一目录。以后仅更新知识库用 `library update`，无需重装 Skill。要改动共享原文，请另存到个人资料目录，避免阻止同步。

## 更新步骤

```text
请从 pantoneray/video-workflow-starter 的 v2.3.22-rc.12 Release 更新我的 Skill。
先阅读 UPGRADE.md，备份旧技能目录，并检查个人配置、账号文件、产物是否混放其中。
保留它们和全部原素材，把个人文件留在包外项目目录。
核对新版 ZIP 的 SHA256，使用完整包替换技能代码，在最终目录重建需要的依赖。
不要搬运旧虚拟环境，也不要把 .env、OAuth文件或个人配置提交到仓库。
本次先补装内置知识库：检查 Git，执行 library setup 并登记到原项目配置；
已有同一仓库目录就复用，不移动资料。再运行 project sync。
保留现有译审选择，只有我需要使用或调整译审服务时再引导配置，密钥不贴聊天。
已有项目运行 project sync，保留已有规则和个人备注，再做环境和离线检查。
刷新 Codex 后告诉我实际可用功能及缺项，安装期间不上传、不付费生成。
```

在包目录重新执行需要的 `sh ./install.sh base`、`packaging`、`align`、`heygen` 或 `youtube`；不必全装。已有项目运行：

```bash
python3 workflow.py project sync --config <项目/video-config.json> --project-root <项目目录>
```

项目尚未初始化时用 `project init`。升级脚本不是自动更新器：当前须由本人或Codex按上述步骤操作，不能声称更新自动保留一切配置。路径变化时先修正包外配置。

## 回滚

停止本次本地审核服务，保留新任务产物与收据，将新版Skill另存备份。恢复旧包到原技能位置并重建其依赖，刷新Codex；如果为新版改过模型配置，恢复对应旧配置副本。旧任务沿用旧记录，新版审批不复制给旧任务。不删除包外个人数据。

## 以后如何获取更新

查看仓库 Releases 的版本及升级说明，再决定是否升级；下载 README 指定版本，`latest`可能指向其他版本。暂未提供自动版本检查器。各版本完整ZIP和SHA256文件用于核对下载内容，旧版本可用于回滚。
