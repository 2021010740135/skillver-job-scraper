# 标准岗归类决策契约（Agent → 脚本）

Agent 使用**内置模型**完成标准岗归类后，必须按本文写出 JSON。  
`scripts/scrape_details.py --details-from-decisions` 只认本契约，不再调用任何脚本内 LLM。

相关文件：

| 角色 | 谁写 | 典型路径 |
|------|------|----------|
| 列表本批 | `scrape_list.py` | `data/<搜索词>/list_batch_<batch>.json` |
| 归类输入 | `clean_classify_input.py` | `data/<搜索词>/classify_input_<batch>.json` |
| 归类决策 | **仅 Agent** | `data/<搜索词>/classify_decisions_<batch>.json` |

完整工作流见根目录 `SKILL.md`。本文只约束**单批 JSON**。

---

## 1. 归类输入（清洗 A → Agent）

`schema_version` 必须为 `1`。`jobs[]` **没有** `location` / `job_link` / `security_id` / `lid`。

```json
{
  "schema_version": 1,
  "query": "阶跃星辰",
  "catalog_names": ["Agent工程师", "机器学习工程师"],
  "batch_index": 1,
  "list_start_page": 1,
  "list_end_page": 2,
  "next_list_start_page": 3,
  "city": "上海",
  "jobs": [
    {
      "id": "encrypt_job_id_xxx",
      "title": "Agent 开发工程师",
      "company": "阶跃星辰",
      "boss_title": "技术总监",
      "salary": "30-50K",
      "tags": "Python,Agent"
    }
  ]
}
```

### Agent 归类时读哪些 / 忽略哪些

| 用途 | 字段 |
|------|------|
| **必读（归类依据）** | `catalog_names`（或另读 `position_catalog.json`）、每条 `jobs[].id` / `title` / `company` / `boss_title` / `salary` / `tags` |
| **编排用（不参与模型判断）** | `next_list_start_page` — 详情跑完后决定是否再抓下一批列表 |
| **可忽略** | 顶层 `query` / `target_position_name`、`city`、分页字段（`list_*` / `batch_index`） |

规则：

- `jobs[].id` = BOSS `encrypt_job_id`（与详情/seen 主键一致）
- 输入里的岗位**已排除**猎头 / 人力资源服务 / 匿名空公司；Agent 不必再判实体
- 实习 / 日薪卡片若出现在输入中，Agent **照常归类**，不要自行丢弃
- Agent **只**对 `jobs` 内每条给出归类结果；`jobs` 为空则写 `results: []`
- 不要按搜索词硬套岗名。搜「阶跃星辰」时，对上 58 岗里的哪一个就写哪一个

---

## 2. 归类决策（Agent → 脚本）

`schema_version` 必须为 `1`。

```json
{
  "schema_version": 1,
  "query": "阶跃星辰",
  "results": [
    {"id": "encrypt_job_id_xxx", "position_name": "Agent工程师"},
    {"id": "encrypt_job_id_yyy", "position_name": "机器学习工程师"},
    {"id": "encrypt_job_id_zzz", "position_name": null}
  ]
}
```

### 字段

| 字段 | 要求 |
|------|------|
| `schema_version` | 整数 `1` |
| `query` | 可选；与本次搜索词一致即可，脚本不校验 |
| `results` | 数组；**必须覆盖**对应 `classify_input.jobs` 的每一个 `id`，不多不少 |
| `results[].id` | 与输入 `jobs[].id` 一致 |
| `results[].position_name` | catalog **原名**字符串，或 JSON `null` |

### 路由语义（脚本执行）

| `position_name` | 脚本行为 |
|-----------------|----------|
| 任一 catalog 原名 | 开详情（全部已映射帖，不截断）；写入全局 seen |
| `null` | 写入全局 seen，不开详情 |

不再区分「当前岗 / 他岗」。对上 58 岗的都抓。

### 禁止

- 发明、缩写、改写岗名（必须与 `position_catalog.json` / `catalog_names` 一字不差）
- Markdown 代码围栏、解释性正文包住 JSON（文件内容必须是纯 JSON）
- 缺少某个输入 `id`，或多出未知 `id`
- 用 yes/no 代替 `position_name`

### 写盘后自检清单

1. `json.load` 可解析
2. `results` 的 id 集合 == 输入 `jobs` 的 id 集合
3. 每个非 null `position_name` ∈ `catalog_names`
4. 失败最多重试 **3** 次；仍失败则打断点，**不要**开详情、不要用规则顶替归类

---

## 3. Agent 归类提示（摘要）

1. 读取 `classify_input_*.json` 与 `data/position_catalog.json`（或输入内 `catalog_names`）
2. 对每条 job 互斥归到**唯一**标准岗，或 `null`（主要看 title / company / boss_title / tags / salary）
3. 按上文写出 `classify_decisions_*.json`
4. 跑自检清单
5. 成功后先数累计映射（各批 `position_name != null`）。不够且还能翻页 → 下一页列表；够了或没有下一页 → 再跑详情 CLI（归类后不要加人闸门）
