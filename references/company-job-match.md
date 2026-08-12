# 企业在招岗 ↔ 标准岗匹配契约（Agent → 脚本）

用于 **按企业采集** 流水线：脚本按企业多关键词从 BOSS 召回**列表**后，  
Agent 使用**内置模型**先分流（映射到 Skillver 标准岗 + 打分），**仅录取者再开详情**。

相关文件：

| 角色 | 典型路径 |
|------|----------|
| 匹配输入（脚本从**列表**写出） | `data/yatn/exports/match_input_<batch>.json` |
| 匹配结果（Agent 写出） | `data/yatn/exports/match_scores_<batch>.json` |
| 标准岗 catalog | `data/skillver/position_catalog.json` |

编排见 `scripts/scrape_company_jobs.py` / `SKILL.md`「按企业采集」节。

## 流水线顺序（强制）

```text
列表 --scrape-list
  → 写 match_input --write-match-input（基于列表，无 JD）
  → Agent 按本文写 match_scores
  → 应用分数 --apply-scores（score>70 且有标准岗 → 录取）
  → 仅对录取岗 --scrape-details
  → --export-csv
```

**禁止**先全量开详情再打分。列表阶段允许误杀偏多；**不允许误放**（不该进 58 岗的不要录取）。

---

## 1. 匹配输入（脚本 → Agent）

`schema_version` 必须为 `1`。输入来自**列表卡片**，通常**无 `jd`**。

```json
{
  "schema_version": 1,
  "batch_id": "20260812_1",
  "catalog_names": ["Agent工程师", "机器学习工程师"],
  "jobs": [
    {
      "id": "encrypt_job_id_xxx",
      "legal_name": "MiniMax",
      "brand_name": "MiniMax",
      "title": "AI全栈工程师（Agent方向）",
      "salary": "40-70K·16薪",
      "location": "上海·徐汇区",
      "tags": "3-5年 | 本科",
      "boss_title": "技术招聘"
    }
  ]
}
```

### Agent 必读

- `catalog_names`（或另读 `position_catalog.json`：`position_name` + `job_intent_label`）
- 每条：`id`、`title`、`legal_name` / `brand_name`、`salary`、`tags`、`boss_title`（若有）

### 可忽略

- `location`（业务不按 base 城过滤，仅供参考）
- `batch_id`
- 若偶发带有 `jd`：可参考，但**不得假设**输入含 JD

脚本侧已排除**日薪**（`元/天` 等）；Agent 不必再判日薪。

---

## 2. 匹配结果（Agent → 脚本）

`schema_version` 必须为 `1`。

```json
{
  "schema_version": 1,
  "batch_id": "20260812_1",
  "results": [
    {
      "id": "encrypt_job_id_xxx",
      "position_name": "Agent工程师",
      "score": 82
    },
    {
      "id": "encrypt_job_id_yyy",
      "position_name": null,
      "score": 25
    }
  ]
}
```

### 字段

| 字段 | 要求 |
|------|------|
| `schema_version` | 整数 `1` |
| `batch_id` | 与输入一致（若输入有） |
| `results` | 必须覆盖输入每一个 `jobs[].id`，不多不少 |
| `results[].id` | 与输入 `jobs[].id` 一致 |
| `results[].position_name` | catalog **原名**，或 JSON `null` |
| `results[].score` | 整数 **0–100**：对「**可否开详情并入库**」的置信度，不是与岗名的字符串相似度 |

### 脚本录取规则

- 仅当 `score > 70`（即分数 ≥ 71）**且** `position_name` 为合法 catalog 原名 → 开详情并进入后续导出  
- `score <= 70` 或 `position_name` 为 `null` → 跳过（可写入 skip 报告）  
- 默认 CLI：`--min-score 71`

### 禁止

- 发明/缩写岗名（必须与 catalog 一字不差）  
- 要求招聘 `title` 与标准岗**名字面一致**才录取（语义映射即可）  
- Markdown 围栏或解释正文包住 JSON  
- 缺少或多余 `id`  
- 用 yes/no 代替 `position_name` / `score`  
- 因公司是 AI 厂、或标题仅含「AI」就硬塞进标准岗  

### 自检

1. JSON 可解析  
2. `results` 的 id 集合 == 输入 jobs 的 id 集合  
3. 非 null 的 `position_name` ∈ catalog  
4. `score` 为 0–100 整数  
5. 失败最多重试 3 次；仍失败则打断点，不要用规则瞎填分数；**不要**对未录取岗开详情  

---

## 3. 分流策略（Agent 必遵）

### 3.1 目标函数

- **最小化误放**：不该映射到 58 岗的岗位不得给出高分非 null  
- **误杀可接受**：信息不足、过泛、歧义 → `position_name=null` 或低分  

### 3.2 两段式判断

1. **先判意图族**：用 catalog 的 `job_intent_label`（如「AI 应用开发工程师」「AI 算法工程师」）判断主职责是否落入某一族；都不像 → `null`，`score≤40`  
2. **再在族内选唯一** `position_name`；族内两个岗都像、分不出主职责 → **`null`**（宁可不放）  
3. 仅当「族清晰 + 族内唯一最优」才给非 null，并用 `score` 表达开详情把握  

### 3.3 列表证据优先级

| 优先级 | 信号 | 用法 |
|--------|------|------|
| 高 | `title`（去【急】等噪音后） | 主依据 |
| 中 | `tags` / 技能标签 | 技术栈与方向 |
| 低 | `salary` 量级、`boss_title` | 辅助（人事发帖 ≠ HR 岗） |
| 忽略 | `location`、品牌融资文案 | 不参与是否入 58 岗 |

**禁止**用品牌名反推岗位类型。

### 3.4 Score 刻度（开详情资格）

| score | 含义 | 动作 |
|-------|------|------|
| 85–100 | 列表信息已足够，主职责几乎必然是该标准岗 | 开详情 |
| 71–84 | 较像，主岗明确（允许次要歧义） | **开详情**（`score > 70`） |
| 50–70 | 沾边 / 信息不足 / 可能他岗 | **不录取**（即使写了 position_name） |
| 0–49 | 明显非目标或无法判断 | `null`，不开详情 |

硬约束：若存在「也可能是另一标准岗」或「也可能根本不在 58 岗内」的合理竞争假设 → **必须 `null`**（或 score≤70），不得为凑数抬分。

### 3.5 倾向拒收（防误放）

列表阶段命中下列且无清晰研发/产品映射时 → `null`：

- 增长 / 投放 / 运营 / 市场 / 销售 / BD / 商务  
- 纯招聘 HR、行政、财务、法务  
- 与 catalog 无关的业务岗（即使公司是 AI 厂）  
- 标题过泛且无方向词：如单独 `Golang`、`AGI研发`、笼统「研发工程师」  

原则：「像 AI 公司的岗」≠「属于我们的 58 标准岗」。

### 3.6 正向映射示例（非穷尽）

| 列表 title（例） | 期望 |
|------------------|------|
| `国内增长投放专家` | `null`（误放零容忍） |
| `AI全栈工程师（Agent方向）` | `Agent工程师` 或 `AI应用工程师`（族内能唯一再选；不能则 null） |
| `【急急急急】Agent测试开发工程师-支付` | 可映射 **`Agent工程师`**（Agent 向测试开发算应用侧 Agent 工程；勿因「测试」一律 null） |
| `Golang` / 无方向的 `AGI研发` | 过泛 → `null` |

不必 title 字面等于「Agent工程师」；语义落在 Agent 应用工程即可。

---

## 4. Agent 提示摘要（可复制）

```text
你是 Skillver 标准岗分流器。根据企业召回的【列表信息】（无 JD）判断能否映射到
position_catalog 中的唯一标准岗。

目标：宁可漏过（误杀），绝不误放。不确定 → position_name=null。
禁止：要求 title 与标准岗名字面一致；禁止因公司是 AI / 标题仅含 AI、Agent 就入选。

步骤：
1) 规范化 title（去急招符号等）
2) 判断主职责是否落入某一 job_intent_label；否则 null
3) 在该意图族内选唯一 position_name；分不出唯一最优 → null
4) score = 对「开详情资格」的置信度；仅 score>70 且非 null 会被脚本开详情
5) Agent 向测试开发（如 Agent测试开发工程师）可归 Agent工程师
6) 输出纯 JSON：覆盖每个 id；position_name 为 catalog 原名或 null
```

写盘后跑自检 → 编排方对录取岗执行 `--scrape-details` → 再导出 CSV。
