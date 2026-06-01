# GithubConnector 相关性过滤 + 未标日期降权 设计文档

**日期**:2026-06-01
**起因**:Plan 1–5 跑通后的两个 backlog 项(原代号 #2 / #5)

## 背景

两条相互独立的小优化,合并到一个 spec/plan 里执行:

- **#2**:`GithubConnector` 的关键词列表(`介绍/说明/区别/原理/什么是/如何/为什么/解释`)语言无关、岗位无关,会把 GitHub 仓库里大量的算法/八股(排序算法、TCP、动态规划等)拉进语料,污染 AI PM 这类非算法岗的备考包。
- **#5**:`dedupe_rank._recency_weight` 给 `posted_at=None` 的题打 `0.5`,**高于**已知 >730 天的 `0.3`。这违反了"时效性是硬需求"的原则——未标日期的内容(GitHub 八股、无日期博客)经验上往往**比已知陈旧内容还更老**。

## 设计

### A. GithubConnector 加 `relevance_hints`

在 connector 侧引入"agent 提示词命中"过滤,保持"agent 出判断,脚本做机械活"的分工。

**接口变化**:
```python
GithubConnector(
    repo_raw_urls: list[str],
    fetcher: Callable[[str], str] | None = None,
    relevance_hints: list[str] | None = None,   # 新增
)
```

**`extract_posts_from_markdown` 签名变化**:
```python
def extract_posts_from_markdown(
    md_text: str,
    url: str,
    relevance_hints: list[str] | None = None,   # 新增
) -> list[RawPost]:
```

**过滤语义**:
- `relevance_hints` 为 `None` 或空列表 → 不过滤(向后兼容)
- 有 hints → `_is_question_like` 通过之后,再要求 `any(h.lower() in candidate.lower() for h in hints)`,未命中则丢弃
- 大小写不敏感、子串匹配(不分词)

**SKILL.md 协同**:
- 步骤 3b 文档里说明:dispatch `GithubConnector` 时把当前一轮收割到的术语/岗位别名作为 `relevance_hints` 传入
- 第一轮没有收割结果时,hints 来自步骤 2 的种子查询

### B. 未标日期降权 0.5 → 0.2

`scripts/corpus/dedupe_rank.py:_recency_weight`:
- `posted_at` 为 `None` 时,返回 `0.2`(原 `0.5`)
- `posted_at` 解析失败(`ValueError`)时,返回 `0.2`(原 `0.5`)——两者语义相同:未知日期

新权重梯度:
| 状态 | 权重 |
|---|---|
| ≤365 天 | 1.0 |
| ≤730 天 | 0.6 |
| >730 天 | 0.3 |
| 未标日期 / 解析失败 | **0.2** |

排序结果:未标日期 < 已知 >730 天 < 730 天 < 365 天。

## YAGNI 边界

不做:
- "相关性分数"(命中数加权);只做布尔保留/丢
- 区分 None vs ValueError 的语义(都按未知)
- 修改 `GithubConnector` 现有调用方(`hints=None` 默认值保证兼容)
- 引入第三种权重档(比如 ">1000 天 0.1")

## 测试

**A. GithubConnector**:
- `hints=None` 时与旧行为一致(已有测试覆盖,无需改)
- `hints=["agent","RAG"]` 时,只保留命中题
- `hints=["mcp"]` 时大小写不敏感(命中 "MCP")
- `hints=[]` 时不过滤(等同 None)

**B. dedupe_rank**:
- 更新现有 `test_none_date_weight_between_fresh_and_stale`:断言顺序变为 `fresh > stale > undated`
- 新增 `test_malformed_date_treated_as_undated`:`latest_posted_at="not-a-date"` 与 `None` 权重相同

## 影响面

- `extract_posts_from_markdown` 多一个可选参数 → 已有 3 处测试调用、连接器内部 1 处调用,默认值兼容
- `GithubConnector.__init__` 多一个可选参数 → smoke test 中我手工构造调用,需要更新示例(无现网代码)
- `_recency_weight` 仅内部使用 → 仅 dedupe_rank 测试受影响

## 验收

1. `pytest interview-intelligence/tests/test_github_connector.py interview-intelligence/tests/test_dedupe_rank.py` 全绿
2. `pytest interview-intelligence/tests/` 全绿(回归无破)
3. SKILL.md 步骤 3b 文本更新,可被未来 agent 读到
