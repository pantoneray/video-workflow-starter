# 回译提供方与配置状态

Google Translate 为盲回译首选，Gemini 做独立校对。适配代码已随包提供并通过离线测试，维护方已有首轮真实接口测试记录；每位使用者仍需配置本人账户并验证语料效果，不影响其他已验证功能交付。缺少 Google 配置时，由 Codex 引导补配并保留已有任务和结果；用户也可先继续其他独立步骤。只有用户明确同意本次临时使用 Gemini 回译，才执行并标明实际提供方，不自动改默认配置。

## 将来启用时配置

在包外项目的模型配置中设置 `backtranslation_provider: "google_translate"`、`backtranslation_model: "nmt"`，参考包内 `config/models.example.json`。保留本人 Gemini 的初译/独立校对模型设置。Google 密钥只通过本机安全渠道设置环境变量 `GOOGLE_TRANSLATE_API_KEY`，不写进 JSON、命令参数、聊天或仓库。

当前仅支持 API key，未实现 ADC/OAuth。Cloud Translation 项目、API 权限、计费和真实语料验收由使用者后续配置；不要求为了使用切片、本地检索、字幕或既有已审成片先配置回译。官方设置参考：[Cloud Translation](https://docs.cloud.google.com/translate/docs/setup)。本包不承诺免费额度。

`review create/revise` 检测到缺 key 或旧配置时返回 `needs_backtranslation_choice`，不调用模型、不覆盖现有结果。这不是完成译审：Codex 应引导用户选择补配、先继续其他步骤或本次临时 Gemini。配置就绪后仍需单独授权真实试验，不把本地测试当云服务验收。

## 已验证的本地行为

只发送目标语正文到回译服务，目标为中文；不附原文、术语或文件路径。Gemini 独立翻译和校对分别记录。保存实际提供方、模型、目标稿哈希、字符数与请求次数；账单字符数及 token 未知时不填造值。

明确收到 HTTP 429 时最多三次指数退避；超时或结果未知不自动重发，保留原意图/结果缓存，查清原请求后才考虑显式 `--retry-unknown`。不自动切换供应商。缺配置、错误脱敏、目标语单独发送、缓存和未知结果不重发已做替身测试。

历史 Gemini 回译和旧批准文件不迁移、不改标签；历史 `provider=google` 若指 Gemini，不能重标为 Google Translate。各使用者的账号及实际语料效果仍须分别验证。

## 维护方首轮通路记录（2026-11-17）

维护方交接记录报告：3 条印尼语样本共955字符，官方 NMT 各请求一次成功，缓存重读未新增提供方请求。本打包轮未重复调用该账户，不分发私人原文、项目、密钥或原始回执；实际账单未知。

这只证明维护方该次接口通路，不表示使用者账户已配置、生产已迁移或语义自动通过。对照检查发现概念偏移与程度加重的回译风险；需结合 Gemini 独立校对和人工审核判断，不据回译直接覆盖审定稿。此对照也不冒充新的 Gemini 校对回执。

## 本次临时沿用 Gemini

先询问用户，得到明确同意后，由 Codex 在原 `review create/revise` 指令上添加 `--temporary-gemini-backtranslation --backtranslation-consent "用户本次同意原话或引用"`，并保留 `--confirm-external`。同意仅适用于本次调用，不自动写入默认配置，不自动从历史批准推断。使用旧配置的回译模型；其为 nmt 或缺省时用配置中的 review_model。只发送目标稿，不附原文与术语。审核版本记录实际 provider=gemini、模型和同意来源，不冒充 Google。若更换回译提供方使缓存不匹配，使用新输出文件/目录保留旧结果，不能覆盖或盲重发未知请求。
