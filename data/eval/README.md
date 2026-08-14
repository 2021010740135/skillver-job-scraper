# 标准岗分流评测集（`data/eval`）

通用 **列表 → 58 标准岗 / 拒绝** 分类金标，与具体公司、某次 smoke 抓取解耦。  
样本可来自任意 BOSS 列表；当前 v1 用 MiniMax 列表草稿预填，**须人工改标**。

## 文件

| 文件 | 说明 |
|------|------|
| `skillver_position_route_v1.json` | 分流评测集（列表 → 录取/拒绝；`items[].gold_*`） |
| `skillver_position_mapping_v1.json` | **定岗映射评测集**（用户叫法 → 58 岗 / 拒绝） |
| `scripts/eval_position_route.py` | 分流指标脚本（FPR / Precision@accept） |
| `scripts/eval_position_mapping.py` | 定岗映射指标脚本（岗名准确率 / 误收率） |
| 本 README | 标注约定 + 主指标 |

契约：`references/company-job-match.md`。岗名必须是 `data/skillver/position_catalog.json` 原名或 `null`。

## 标注字段

| 字段 | 含义 |
|------|------|
| `gold_reject` | `true` = 不应进 58 岗（不开详情） |
| `gold_position_name` | 应录取时为 catalog 原名；拒绝时必须 `null` |
| `label_status` | `draft` = Agent/脚本初稿；`human` = 人工确认（正式金标） |

约束：`gold_reject === true` ⇔ `gold_position_name === null`。

人工评测时：逐条改 `gold_*`，确认后把 `label_status` 改为 `human`。未改完前不要用 draft 当正式基线。

## 主指标（仅这两个）

预测侧：对每条样本给出 `pred_position_name`（catalog 原名或 `null`）。  
**录取** 定义：`pred_position_name != null`（与线上 `score>70` 且非 null 对齐；比对脚本可将低分视为拒绝）。

### 1. 误放率 FPR（第一主指标）

\[
\mathrm{FPR} = \frac{\#\{\mathrm{gold\_reject}\land\mathrm{pred\_accept}\}}{\#\{\mathrm{gold\_reject}\}}
\]

金标应拒、预测却录取。目标：**尽量为 0**。

### 2. Precision@accept（第二主指标）

\[
\mathrm{Precision@accept} = \frac{\#\{\mathrm{gold\_accept}\land\mathrm{pred\_accept}\}}{\#\{\mathrm{pred\_accept}\}}
\]

预测录取里真正该录的比例（`gold_accept` = 非 `gold_reject`）。  
与 FPR 互补；预测录取为空时该指标记为 `n/a`。

> 本阶段**不算**岗名是否分对、也不算误杀率。后续若要加「岗准确率」，另开指标。

## 怎么跑比对

预测 JSON 形状与 `match_scores` 相同（`results[].id` / `position_name` / `score`），或简化为：

```json
{"results":[{"id":"...","position_name":"Agent工程师","score":85}]}
```

```bash
python3 scripts/eval_position_route.py \
  --gold data/eval/skillver_position_route_v1.json \
  --pred data/yatn/exports/match_scores_smoke.json \
  --min-score 71
```

`--min-score 71`：`score < 71` 或 `position_name` 为空 → 视为预测拒绝。

## 扩充样本

往 `items` 追加即可（任意公司列表字段 + 人工 `gold_*`）。保持 `id` 稳定；不要把某次模型 `score` 当作金标。

---

## 定岗映射评测集（`skillver_position_mapping_v1.json`）

测**用户叫法/自然语言 → 58 标准岗**的映射准确率（与分流评测互补：分流测"录不录"，这里测"归哪个岗"）。

### 字段

| 字段 | 含义 |
|------|------|
| `input` | 用户叫法/自然语言描述（如「搞机器学习的岗位」） |
| `gold_position_name` | 应映射的 catalog 原名；应拒时为 `null` |
| `kind` | `alias`（规则表应唯一命中）· `semantic`（规则零命中，语义兜底负责）· `reject`（应拒）· `ambiguous`（多候选歧义，线上走人工确认，**自动评测跳过**） |
| `label_status` | `draft`（初稿）→ `human`（人工确认，正式金标） |

### 指标（仅两个）

1. **岗名准确率 position_accuracy**：`pred == gold` 的条数 / 可评测条数（`kind != ambiguous`）
2. **误收率 false_accept_rate**：金标应拒（null）但预测录取 / 应拒总数

### 怎么跑

预测 JSON 形状同 `match_scores`（`results[].id` / `position_name` / `score`），
`position_name` 为空视为预测拒绝；缺失 id 视为拒绝。

```bash
python3 scripts/eval_position_mapping.py \
  --gold data/eval/skillver_position_mapping_v1.json \
  --pred data/yatn/exports/pred_map.json
```

### 扩充样本

`items` 追加即可。`alias` 类可从 `position_aliases.json` 每岗取代表叫法；
`semantic` / `reject` / `ambiguous` 手工补充真实用户说法。保持 `id` 稳定；
`gold_position_name` 必须是 `position_catalog.json` 原名或 `null`。
