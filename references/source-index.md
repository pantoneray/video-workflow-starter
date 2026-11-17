# 复用已有全集索引

可选配置（写在使用者个人配置；不要把私人路径打包）：

```json
{
  "source_index": {"type": "paragraph_fts", "path": "./my-corpus.sqlite"},
  "paths": {"subtitle_sources": ["./subtitles"]}
}
```

`source-select` 的 `auto/corpus/srt` 三种选择保持原接口。明确配置索引后，全集来源采用该索引，不再把原始文本目录作为另一套全集扫描。未配置索引则保留现有文件检索。SRT 独立检索；选择 srt 不访问全集索引。索引不可读或结构不支持时报告 index_unavailable，不自动创建/重建数据库、不静默换库。缺失某类资料会显示 missing_types。

目前支持已有 paragraphs + paragraph_fts（FTS5）结构。paragraphs 必须含 id、book_id、book_title、chapter、paragraph_index、source_epub、source_xhtml、text；FTS rowid 对应 paragraphs.id。连接使用 mode=ro、query_only、查询时间上限，现有库不变。没有重新建立索引，不支持任意数据库结构，也不宣称实现向量 RAG。

关键词按现有 FTS 分词匹配正文、书名或章节；不等同于任意中文子串匹配。结果受数量上限和排除词限制，零命中不证明没有相关原文。相同全文合并候选，但保留其他出处；相似段落不会擅自合并。

每条包含完整原段、书名/章节/段落号、原 EPUB/XHTML 索引定位及同章节前后段。source 字段可以直接用于 hook-copy/T1；审核页重新读取索引行及上下文，比对记录哈希。任何文字或定位变化都会拒绝沿用旧证据。哈希覆盖索引记录，不是整个数据库或原 EPUB；原典逐字核验与人审仍须保留。不要把索引抽取错误当成已验证原话。

2026-11-17 开发验证：临时真实 SQLite 的只读、上下文变更拒绝、重复合并、缺库不创建和纯 SRT 选择通过；维护方另报告已有全集只读检索5条并生成一条待审T1；本打包轮不复制真实资料，也不把该提案视为用户批准。私人路径、原文及回执不分发。安装者仍须配置自己的资料库。
