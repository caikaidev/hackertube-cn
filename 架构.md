# HackerTube CN 架构

一句话：**数据源可插拔，中间语料只有一个格式，下游全部源无关。**

```
数据源            适配器                 统一语料             加工（源无关）            呈现
─────────        ─────────────          ─────────────        ──────────────────      ─────────
V2EX 官方 API ─┐
SOV2EX 发现   ─┴→ sources/v2ex.py  ─→  data/parsed/     ─→  extract_chunked.py  ─→  build_site.py
(未来) HN/RSS ──→ sources/<name>.py ─→  topic_*.json        fetch_covers*.py         site/index.html
                                            │               fetch_banners.py         site/feed.xml
                                            └─ corpus.py    find_episodes.py
                                               统一加载
```

## 分层

1. **适配器层 `pipeline/sources/`**：每个数据源一个模块，实现 `base.py` 的契约：
   - `discover(queries)`：找候选主题（如 V2EX 走 SOV2EX 搜索 + 官方 API 复核回复数）；
   - `fetch(topic_id)`：抓一个主题并产出统一语料（见下），带 `"source"` 字段。
   注册表在 `sources/__init__.py` 的 `SOURCES`。V2EX 的回复边规则（#N > @用户 > 文字「X楼」）是适配器内部事务，在 `parse_floors.py`。
2. **统一语料层 `pipeline/corpus.py`**：所有主题都是同一 schema（字段定义见 corpus.py 文件头），存 `data/parsed/topic_<id>.json`。消费者一律经 `load_topics()` 读取，按 `(source, topic_id)` 索引——不同源的数字 id 可以重名不冲突。条目的每条来源引用同样带 `source` 字段；缺失时默认 `v2ex`（兼容存量）。
3. **加工层（源无关）**：`extract_chunked.py`（LLM 提取+名字命中校验+时政名单过滤）、`fetch_covers*.py`（头像/粉丝回填）、`fetch_banners.py`（封面）、`find_episodes.py`（单集归属，平台接口核对作者）。它们只认统一语料与条目，不出现任何站点专属逻辑。
4. **呈现层**：`build_site.py` 生成单文件零依赖静态站（+ RSS）。构建时从语料摘原话、算首提/最近提及时间。

## 新增一个数据源（清单）

1. 在 `pipeline/sources/` 新建 `<name>.py`，实现 `discover/fetch`，`fetch` 产出统一 schema 并写 `data/parsed/`（或返回 dict 由 CLI 落盘）；
2. 在 `sources/__init__.py` 注册；
3. 用适配器抓若干主题 → 跑 `extract_chunked.py` → 跑富化脚本（按需）→ `build_site.py`；
4. 若新源的楼层结构没有「回复边」，在适配器里给出合理的 `parent_floor`（全顶层也可，佐证规则会降级为同帖多次提及）；
5. 页面页脚的来源链接、原话摘录、首提时间都走语料字段，无需改前端；只有想在卡片上标出来源名时，才动 `build_site.py` 的 `source_topics` 渲染。

## 当前数据源

| source | discover | fetch | 备注 |
|---|---|---|---|
| v2ex | SOV2EX（size≤50、sort=created；回复数回官方 API 复核） | 官方 API v1 → `parse_floors.py` 边规则 | 14 帖 / 1,348 楼（2026-11-02） |
