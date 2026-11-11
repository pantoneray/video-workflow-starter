# 文件夹批量切片、主题与审核

## 批量切片

可以说：“扫描这个文件夹，优先清晰源片，总共输出 20 条 30–45 秒切片，每个视频最多 3 条，同时处理 2 个视频。”

Agent 先明确总数量、每源片上限及顺序/并行。默认顺序处理（workers=1），有限并行可选 2–4；机械扫描可并行，动作审核仍逐条落实。完整扫描每个源片，可从同一源片选多条。数量不足就报告缺口，不降低质量凑数。

```sh
python3 workflow.py batch-clips scan --folder "素材文件夹" --rules config/selection-rules.example.json --out "包外新扫描目录" --count 20 --per-video 3 --workers 2
```

默认递归发现视频，按短边分辨率、像素数降序，同级按文件名排序；`--order name` 改为文件名顺序。分辨率只是清晰度初筛，须继续检查实际模糊、压缩失真与动作。优先原始清晰素材，不能用放大的分辨率冒充更清晰。每个视频独立保存 coverage.json，失败记录在 batch.json，不影响其他视频扫描。

读取 batch.json，复用 `scan review` 连续预览与动作审核。Agent 根据实际审核填写 selections.json，结构如下（路径由 Agent 填写，用户不用手写）：

```json
[{"report":"某视频的coverage.json路径","candidate_ids":[1,3],"review_file":"对应review.json路径"}]
```

只填合格且不重叠的候选。可在同一视频选择多条；优先顺序沿用批次顺序。运行：

```sh
python3 workflow.py batch-clips export --batch "扫描目录/batch.json" --selections "selections.json" --out "新切片目录"
```

入口复用原有审核校验和 FFmpeg 切片程序，按总数量及每片上限输出，保存 batch-result.json；输出后沿用 qc 检查并提供用户播放链接。候选数量不等于合格数量。为控制资源，最终导出顺序执行。Windows 将 python3 换为 python。批次输出须使用新目录；扫描输出放在素材文件夹外，避免再次扫入产物。

## 主题选择与确认后保存

主题文件放在使用者项目中，例如 `topics.json`，首次可复制 `config/topics.example.json` 并按资料范围调整。先只读取主题 ID、名称、简短说明给用户选择；选中后才加载该主题的关键词、受众和资料范围。用已有 `source --themes ... --theme-id ...` 检索；限制候选数量，按需补读上下文，不把整库塞进聊天。

用户提出新主题时先用于本次任务，询问“是否加入你的主题库，供以后选择？”只有明确同意才写入项目主题库。记录确认来源与时间，保留更新前副本；不同意或未答复就不长期保存。不改全局记忆、不把私人主题写回分发包。

## 审核文件在哪里

每次运行在用户指定输出目录下建立独立任务目录。审核文件统一放 `审核/`：`译审-v1.md` 是供人阅读的原文、译文、独立译文、盲回译、疑点及前后变化；`v1.json`、`决定-v1.json` 保存版本与明确反馈。用既有 review-packet 生成 Markdown，review decide 保存用户决定。修订另存 v2，不覆盖旧版。

Agent 完成后必须给出审核文件的可点击绝对路径，简述待确认点。用户可在聊天里逐条提出通过、修改、拒绝或暂缓，由 Agent 如实记录，无需用户编辑 JSON。未回复的项目保持待审。

## 标题和简介由谁出

Codex 调用现有 metadata 脚本，由用户配置的 Gemini 模型根据获批文案和目标语言生成标题、简介、标签候选；Codex 展示给用户审核。用户自己提供的版本同样可用。候选保存在本次任务的 `发布资料/metadata-v1.json`，并在聊天中展示可读文字；用户确认后沿用 publication-review 和 YouTube 私密上传。无需增加 Agent 或改变既有译审分工。
