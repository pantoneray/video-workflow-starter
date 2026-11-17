> 新用户先读[逐步安装使用](GETTING_STARTED.md)，老用户先读[升级配置与回滚](UPGRADE.md)。

# 2.3.22-rc.10 更新报告

GitHub 预发布交付版；核心代码与已审 rc.10 一致，补充面向使用者的文档。

## 实际改动

在 rc.9 基础上，project init 自动写入通用制作规则，project sync 更新受管区域并保留个人备注；安装依赖不修改全局规则。README 统一说明 Notion 是可选开发适配、统一 delivery 清单按需启用。切片、译审、HeyGen、字幕模板和 YouTube 核心脚本保留。

回译保持 Google Translate，Gemini 负责独立校对；没有三提供方自动降级链。缺配置明确停止。

## 安装和使用

使用本地 ZIP 与校验文件，按 LOCAL-RELEASE.md 和 references/mac-first-install-check.md 安装。个人配置放包外；配置路径后运行 project init，已有项目用 project sync。自然语言指定素材、数量、主题和目标语种即可分步启动；账号、审核和付费授权仍由本人完成。

## 测试

116 项 Python 测试通过、无跳过；Node 页面交互、Skill 结构、check-env 及同机全新目录 base 安装和项目初始化通过。ZIP 逐文件 SHA256、CRC、敏感文件名和文本模式检查通过；未运行 Gitleaks。完整结果见 ZIP 旁 ACCEPTANCE.json 和 python-tests.log。离线测试不等于真实账号或跨设备全流程验收。

## 限制

另一台 Mac 尚未验证，不阻塞交付。审核旧版后自动打开新版未实现，不阻塞人工打开链接。可选 Notion 注册与真人批准未验；未纳入后续未测试的页面登记代码。包装钩子历史预览约8.5秒，未满足约3秒目标，仍需选句与听审。没有携带私人素材或凭据，不承诺完整无人值守生产。

## 更新与回滚

当前使用完整 ZIP 手动更新，没有自动检查版本或保留配置的更新器。备份旧 Skill，个人配置和产物留包外，在新位置重建依赖；运行 project sync 更新本项目受管规则。回滚恢复旧包并重建依赖，不搬迁批准或覆盖历史收据。本次已获授权发布为预发布版；后续更新仍需明确授权。
