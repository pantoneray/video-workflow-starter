# 共享知识库安装、更新和选文

## 安装时一起准备

包内已配置知识库地址 `https://github.com/smartlib-lab/suodj.git`，内容涵盖著作、译作、课程、开示和大学演讲。首次安装 Skill 时，Codex 在用户提供项目位置后准备配置，检查并按需安装 Git，执行以下步骤。正文首次需联网下载，不随每次发布 ZIP 重复分发；不需要知识库 API、模型密钥或 Smart Library 软件。用户明确不用此库可跳过，既有其他功能照常使用。

所有命令从 Skill 目录调用，尖括号替换为本人路径：

```bash
python3 workflow.py env --with-library
python3 workflow.py library setup --config <项目/video-config.json>
python3 workflow.py project init --config <项目/video-config.json> --project-root <项目目录>
```

已有本包项目记忆时最后一步用 `project sync`。`library setup` 默认下载到配置文件同级的 `资料库/suodj/`，登记 `libraries.suodj`。保留原有路径、模型和账号配置，改配置前留一份 `.before-library-*.bak`；重复运行复用原登记路径，不重装。

如果已经用 Smart Library 下载了同一仓库：

```bash
python3 workflow.py library setup --config <项目/video-config.json> --path <已有suodj本地目录>
```

原目录必须是对应的干净 Git 仓库，不能用普通文件夹冒充；不移动、不强制改源。选文和更新期间不要让另一工具同时同步该目录。新用户无需先下载 Smart Library。

## 平时使用

> 更新知识库，从我选定的主题中找文案，保留真实出处和上下文，给我审核。

Codex 先同步、再检索，不向共享库写笔记、主题、审核结果或生成文件。

```bash
python3 workflow.py library status --config <项目/video-config.json>
python3 workflow.py library update --config <项目/video-config.json>
python3 workflow.py source --config <项目/video-config.json> --themes <项目/topics.json> --theme-id <选中主题ID> --out <本次任务/03_翻译与审核/candidates.json>
```

`status`只检查本地，不声称与远端相同。`update`用Git拉取新增、修改和删除，只接受快进更新，不强制reset、不上传。本地有个人修改、源地址不符或正在运行时，保留数据并提示处理。网络失败返回 `update_unavailable`，Codex询问是否沿用已下载版本；用户指定离线时不执行更新。

`source`和`source-select`均支持已登记共享库。若显式配置了旧SQLite索引，`source-select`仍以该索引定义的范围为准，不静默混库；要查询共享库可用`source`。目录按`.meta.json`章节顺序扫描，保存书名、相对路径、行号、上下文和相邻章节定位；标签仅为资料元数据，不自动推断作者或讲者。

原有个人资料路径仍保留。主题的 `source_scope` 可用 `life_corpus` 或 `deep_corpus`；可选 `library_ids: ["suodj"]` 指定库。本人配置 `libraries.suodj.directories` 可缩小到 `著作`、`课程` 或具体书籍目录。禁用时设 `enabled: false`，不删除本地资料。

## 文件与更新规则

```text
本人项目/
├── video-config.json
├── topics.json
├── 资料库/suodj/               共享原文，只读使用
└── 输出/本次任务/03_翻译与审核/
    ├── candidates.json        候选、出处和知识库版本
    └── candidates.json.sources/  本次用到的全文和章节元数据快照
```

文件检索复用现有选文脚本，分文件处理大库，不受原先单次500文件限制；仍是关键词召回，不承诺找到全部语义相关内容。只返回候选和必要上下文，不把全库送入聊天。达到候选上限即停止，结果会说明范围。图片标记不能作为口播文本；混合标记的段落需选取干净原句并重新核对逐字范围。

CLI保存的快照可直接交本地审核与译审；原文和元数据哈希可核查，知识库后续修改或删除不改旧任务。直接用Python函数检索只返回现场候选，需要调用`freeze_report`后再长期审核。更新发现更正时，由用户决定是否重选、改稿和重审，不自动继承旧批准。

Skill 升级使用新完整包，资料目录保留，不重新下载；资料库升级只用 `library update`。不要把下载的正文、个人配置或任务快照提交回 Skill 仓库。共享资料仍按提供方的使用条件引用，不把公开可访问等同于可随意再分发。
