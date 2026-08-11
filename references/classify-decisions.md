# 标准岗归类决策契约（Agent → 脚本）

Agent 使用**内置模型**完成标准岗归类后，必须按本文写出 JSON；  
`boss_cdp_raw.py --details-from-decisions` 只认本契约，不再调用任何脚本内 LLM。

相关文件：

| 角色 | 典型路径 |
|------|----------|
| 归类输入（脚本 `--list-only` 写出） | `data/skillver/exports/classify_input_<岗>_<batch>.json` |
| 归类决策（Agent 写出） | `data/skillver/exports/classify_decisions_<岗>_<batch>.json` |

---

## 1. 归类输入（脚本 → Agent）

`schema_version` 必须为 `1`。

```json
{
  "schema_version": 1,
  "target_position_name": "Agent工程师",
  "catalog_names": ["Agent工程师", "机器学习工程师"],
  "batch_index": 1,
  "list_start_page": 1,
  "list_end_page": 2,
  "next_list_start_page": 3,
  "jobs": [
    {
      "id": "encrypt_job_id_xxx",
      "title": "Agent 开发工程师",
      "company": "示例科技",
      "boss_title": "技术总监",
      "salary": "30-50K",
      "tags": "Python,Agent",
      "job_link": "https://www.zhipin.com/job_detail/xxx.html"
    }
  ]
}
```

规则：

- `jobs[].id` = BOSS `encrypt_job_id`（与详情/seen 主键一致）
- 输入里的岗位**已排除**猎头 / 人力资源服务 / 匿名空公司（脚本规则）；Agent 不必再判实体
- Agent **只**对 `jobs` 内每条给出归类结果

---

## 2. 归类决策（Agent → 脚本）

`schema_version` 必须为 `1`。

```json
{
  "schema_version": 1,
  "target_position_name": "Agent工程师",
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
| `target_position_name` | 与本次 `--position-name` / 输入中的目标岗**完全一致**（catalog 原名） |
| `results` | 数组；**必须覆盖**对应 `classify_input.jobs` 的每一个 `id`，不多不少 |
| `results[].id` | 与输入 `jobs[].id` 一致 |
| `results[].position_name` | catalog **原名**字符串，或 JSON `null` |

### 路由语义（脚本执行）

| `position_name` | 脚本行为 |
|-----------------|----------|
| 等于 `target_position_name` | 当前岗 → 开详情 |
| 其它 catalog 原名 | 他岗 → 写入该岗 `pending_details` 库存 |
| `null` | none → 不写库存、不开详情 |

### 禁止

- 发明、缩写、改写岗名（必须与 `position_catalog.json` / `catalog_names` 一字不差）
- Markdown 代码围栏、解释性正文包住 JSON（文件内容必须是纯 JSON）
- 缺少某个输入 `id`，或多出未知 `id`
- 用 yes/no 代替 `position_name`

---

## 3. Agent 归类提示（摘要）

1. 读取 `classify_input_*.json` 与 `data/skillver/position_catalog.json`（或输入内 `catalog_names`）
2. 对每条 job 互斥归到**唯一**标准岗，或 `null`
3. 按上文写出 `classify_decisions_*.json`
4. 自检：JSON 可解析、`results` 与输入 id 集合相等、岗名合法
5. 失败最多重试 **3** 次；仍失败则打断点，提示用户「修好后回复继续」，**不要**开详情、不要用规则顶替归类

---

## 4. 脚本调用（分步）

```bash
# 清当前岗库存（不经 Agent）
python3 scripts/boss_cdp_raw.py --position-name "<岗>" --drain-inventory

# 一批列表 → 写出 classify_input
python3 scripts/boss_cdp_raw.py --position-name "<岗>" --city <城市> \
  --list-only --list-start-page 1 --page-batch-size 2

# Agent 写好 decisions 后开详情
python3 scripts/boss_cdp_raw.py --position-name "<岗>" \
  --classify-input data/skillver/exports/classify_input_<岗>_1.json \
  --details-from-decisions data/skillver/exports/classify_decisions_<岗>_1.json
```
