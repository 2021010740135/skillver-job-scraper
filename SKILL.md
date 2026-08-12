---
name: skillver-job-scraper
description: >
  通过本机已登录 Chrome（CDP）按 Skillver 标准岗分步采集公开职位，由 Agent 内置模型归类，
  导出 Skillver job_YYYYMMDD.csv，并用 Agent 网络检索补全统一社会信用代码与工商全称。
  用户提到 Skillver、标准岗、--position-name、按企业采集、YATN、职位采集、
  BOSS直聘、zhipin、USCC、统一社会信用代码、工商全称、企业信用代码、
  公司主体补全，或要从详情导出招聘 CSV 时，应优先使用本 skill；即使未点名
  skill 名，只要任务属于该流水线也应触发。本 skill 必须人机协同：登录数据源、
  核验 USCC 歧义主体、核验最终 CSV。禁止用企查查/Selenium 批量爬工商；
  禁止在脚本内再调 DeepSeek 或其它 API 做归类。
version: 2.6.0
author: skillver-job-scraper
license: MIT
platforms: [macos, linux, windows]
metadata:
  hermes:
    tags: [scraper, jobs, career, cdp, chrome, skillver, uscc, zhipin]
---

# Skillver 职位采集（skillver-job-scraper）

面向 WorkBuddy / Hermes / Claude Code **或任意 Agent** 的 **公开职位 → Skillver CSV** 执行手册（最小稳定集，v2.5.1）。当前采集适配为 BOSS直聘；编排与目录按 Skillver 标准岗流水线组织。

**只读本文件 + `references/classify-decisions.md` 即可跑完主路径。** 不要另写爬虫，不要在脚本内调 DeepSeek。

## 项目链接

- 仓库：本 skill 所在 git 根目录（含 `scripts/`、`data/`、`references/`）

## 这个 skill 具备的能力

1. 启动本机调试 Chrome，并引导用户登录 BOSS直聘
2. 按标准岗抓取列表（规则过滤猎头/匿名），**用 Agent 内置模型归类**
3. 按决策文件只开「当前岗」详情；他岗写入库存
4. 导出 Skillver `job_YYYYMMDD.csv`
5. 对空缺 USCC / 工商全称做网络检索，经用户确认后写 cache 并**原地回填 CSV**
6. 用户核验最终 CSV 前，不宣布任务完成

## 执行原则

1. **先判定任务阶段，再执行** — 登录 / 清库存 / 列表 / 归类 / 详情 / 导出 / USCC / CSV 核验
2. **优先复用 scripts + references** — 不要另写爬虫或脚本内 LLM
3. **标准岗唯一主路径** — 必须 `--position-name`（`position_catalog.json` 原名）
4. **归类只用 Agent 内置模型** — 按 `references/classify-decisions.md` 写决策 JSON
5. **人机闸门仅三处** — `WAIT_LOGIN` / `WAIT_USCC_REVIEW` / `WAIT_CSV_REVIEW`（归类成功后**不要**加人闸门，直接开详情）
6. **稳优先于快** — 详情间隔保持脚本默认；限流/验证码则停，不硬闯
7. **社招主路径不处理日薪**（`元/天`）— 导出侧会跳过无法解析为 `N K-M K` 的薪资

## Scripts guide

```bash
SCRAPER=scripts/boss_cdp_raw.py
EXPORT=scripts/export_skillver_csv.py
COMPANY=scripts/scrape_company_jobs.py
REF=references/classify-decisions.md
REF_COMPANY=references/company-job-match.md
```

| 资源 | 用途 |
|------|------|
| `scripts/boss_cdp_raw.py` | 标准岗 CDP：`--drain-inventory` / `--list-only` / `--details-from-decisions` |
| `scripts/export_skillver_csv.py` | 标准岗详情 → Skillver CSV + seen + USCC |
| `scripts/scrape_company_jobs.py` | **按企业**采集在招岗 → Agent 打分 → 后端 CSV |
| `references/classify-decisions.md` | 标准岗归类契约 |
| `references/company-job-match.md` | 企业岗 `score` + 标准岗契约 |
| `data/yatn/companies.csv` | YATN 企业名单（S/A） |
| `data/city_codes.json` | 城市码 |
| `data/skillver/position_catalog.json` | 58 标准岗 |

### 关键默认值（以脚本为准）

| 项 | 默认 |
|----|------|
| `--cdp-port` | `9222` |
| 专用 Chrome profile | `~/.boss-zhipin-scraper/chrome-profile` |
| `--city`（抓取） | `上海` |
| `--pages`（标准岗硬上限） | `8`（全局上限 10） |
| `--page-batch-size` | `2` |
| `--list-start-page` | `1` |
| `--batch-index` | `1` |
| `--min-details` | `5`；上限 `50`（超限压到 50 并打印提示） |
| `--login-timeout` | `300` 秒 |
| 列表 JSON | `data/skillver/jobs/boss_jobs_<岗名>.json` |
| 详情 JSON | `data/skillver/details/boss_details_<岗名>.json` |
| seen | `data/skillver/seen_jobs.json` |
| 导出 CSV | `data/skillver/exports/job_YYYYMMDD.csv` |
| USCC cache | `data/skillver/company_uscc_cache.json` |
| match skip 报告 | `data/skillver/exports/match_skip_<岗名>.json` |
| 决策报告 | `data/skillver/exports/decisions_<岗名>.json` |

### `--min-details`（强制理解）

- 含义：**本轮目标新增**详情数，**不是**历史累计已有数
- 默认 **5**；`<1` 按默认；`>50` 压到 **50** 并提示
- **Agent 循环**决定是否继续 `--list-only`；**单次脚本调用不自动循环**翻页归类
- drain 后若本轮新增已 ≥ 目标，可跳过列表循环，直接导出

### 分步模式互斥（标准岗必选其一）

同一调用只能选一个：

1. `--drain-inventory`
2. `--list-only`
3. `--details-from-decisions PATH`（必须同时给 `--classify-input`）

### 城市与 location（2.5.1）

- list / drain / details **建议都带** `--city <中文或代码>`
- 2.5.1 起：详情会提取/透传 `location`；list-only 写入 `jobs[].location` 与顶层 `city`
- 导出：详情有 `location` 时**可不传** `--city` 也能写出「所在城市」
- **旧空 location 详情**仍建议导出时传 `--city` 作回退

---

## CLI 速查（可复制）

### 环境

```bash
python3 "$SCRAPER" --check --cdp-port 9222
python3 "$SCRAPER" --setup-chrome --cdp-port 9222
# 可选：--login-timeout 300  --no-wait-login  --copy-login-state  --reset-chrome-profile
python3 "$SCRAPER" --stop-chrome --cdp-port 9222
python3 "$SCRAPER" --list-cities 上海
```

### 抓取分步

```bash
# 清当前岗库存（建议带 --city，作详情 location 回退）
python3 "$SCRAPER" \
  --position-name "<标准岗名>" \
  --city 上海 \
  --drain-inventory

# 一批列表 → classify_input
python3 "$SCRAPER" \
  --position-name "<标准岗名>" \
  --city 上海 \
  --list-only \
  --list-start-page 1 \
  --page-batch-size 2 \
  --batch-index 1 \
  --pages 8 \
  --min-details 5
# 可选筛选（experience/scale 可逗号或重复）：
#   --experience 105 --scale 305,306 --salary 406 --degree 203 --stage 807 --industry 1001

# Agent 写好 decisions 后开详情
python3 "$SCRAPER" \
  --position-name "<标准岗名>" \
  --city 上海 \
  --classify-input data/skillver/exports/classify_input_<岗>_<B>.json \
  --details-from-decisions data/skillver/exports/classify_decisions_<岗>_<B>.json
# 可选显式报告路径（标准岗默认会写 match_skip_*/decisions_*）：
#   --match-report data/skillver/exports/match_skip_<岗>.json
#   --decision-report data/skillver/exports/decisions_<岗>.json
```

### 导出

```bash
python3 "$EXPORT" \
  --details data/skillver/details/boss_details_<岗名>.json \
  --position-name "<标准岗名>" \
  --city 上海 \
  --dry-run

# 确认后去掉 --dry-run；可加 --append / --report PATH / --uscc-cache PATH
```

---

## 单批 JSON（摘要；权威见 references）

| 角色 | 谁写 | 典型路径 |
|------|------|----------|
| 归类输入 | 脚本 `--list-only` | `data/skillver/exports/classify_input_<岗>_<B>.json` |
| 归类决策 | **仅 Agent** | `data/skillver/exports/classify_decisions_<岗>_<B>.json` |

强制自检（写 decisions 后、开详情前）：

1. 文件是**纯 JSON**（无 Markdown 围栏、无解释正文）
2. `schema_version === 1`
3. `target_position_name` 与本次 `--position-name` / 输入完全一致
4. `results` 的 `id` 集合与输入 `jobs[].id` **相等**（不多不少）
5. 每个 `position_name` 是 catalog **原名**或 JSON `null`

失败：最多重试 **3** 次 → 打断点，提示用户「归类失败，修好后回复继续」→ **不开详情、不用规则顶替归类**。

输入侧脚本可能写入顶层 `city`、`jobs[].location`——**归类可忽略**；详情/导出会用。完整字段与路由语义见 `references/classify-decisions.md`。

---

## 工作流

### Step 1：识别目标

- **目的**：锁定本轮跑什么，避免跑错岗或漏闸门
- **命令**：无（问用户 / 读需求）
- **产出 / 成功判据**：确认下列全部有值或明确「不需要」  
  - `position_name`（catalog 原名）  
  - 城市（默认上海）与可选筛选  
  - `--min-details`（默认 5）  
  - 是否只要导出 / 只要补 USCC（可跳过抓取）
- **失败 / 人机闸门**：岗名不在 catalog → 停，让用户改名；不要发明岗名

### Step 2–3：环境与登录

- **目的**：CDP 可用 + BOSS 已登录（明文薪资接口可用）
- **命令**：

```bash
python3 "$SCRAPER" --check --cdp-port 9222
# 不通则：
python3 "$SCRAPER" --setup-chrome --cdp-port 9222
```

- **产出 / 成功判据**：`--check` 报告 CDP 就绪且已检测到登录态
- **失败 / 人机闸门**：  
  - 进入 **`WAIT_LOGIN`**，等用户回复「已登录」后再跑 `--check`  
  - 依赖缺失 → `pip install -r requirements.txt`（仅 `requests` + `websocket-client`）  
  - **不需要** `.env` / DeepSeek  
  - 限流/验证码/风控 → **停止**并提示用户，不硬闯  
  - 抓完可 `python3 "$SCRAPER" --stop-chrome`（只关专用 profile，不碰主 Chrome）

### Step 4a：清当前岗库存

- **目的**：打开当前岗 `pending_details` 里已挂账、未抓详情的岗位（不经 Agent 归类）
- **命令**：

```bash
python3 "$SCRAPER" \
  --position-name "<标准岗名>" \
  --city 上海 \
  --drain-inventory
```

- **产出 / 成功判据**：日志出现库存/本轮新增；详情写入 `data/skillver/details/boss_details_<岗名>.json`；seen 更新
- **失败 / 人机闸门**：未登录 → 回 Step 2–3；无 pending 则新增为 0，正常继续  
  - 若本轮新增详情已 ≥ `min-details` → **跳到 Step 5**

### Step 4b：按批循环（直到够数或无新列表）

对每一批 `B=1,2,…`，顺序固定：**list-only → 写 decisions → details-from-decisions**。归类成功后**不要**等人确认。

#### 4b-1）列表

- **目的**：抓一批列表页，过滤猎头/匿名/已见，写出 classify_input
- **命令**：

```bash
python3 "$SCRAPER" \
  --position-name "<标准岗名>" \
  --city 上海 \
  --list-only \
  --list-start-page <N> \
  --page-batch-size 2 \
  --batch-index <B> \
  --pages 8 \
  --min-details <目标>
```

首批 `N=1`；下一批 `N` = 上批 classify_input 的 `next_list_start_page`。

- **产出 / 成功判据**：  
  - `data/skillver/exports/classify_input_<岗>_<B>.json`  
  - 记下 `next_list_start_page`（`null`/缺失表示无更多页）  
  - `jobs` 可为空（本批无可归类卡片）
- **失败 / 人机闸门**：登录失效/限流 → 停并提示用户

#### 4b-2）Agent 归类（内置模型）

- **目的**：为 classify_input 中每条 job 互斥归到唯一标准岗或 `null`
- **命令**：无脚本；读 `$REF`，写 decisions 文件
- **产出 / 成功判据**：  
  - `data/skillver/exports/classify_decisions_<岗>_<B>.json`  
  - 通过上文「强制自检」
- **失败 / 人机闸门**：最多 **3** 次重试 → 打断点（等用户「继续」）；**不开详情、不用规则顶替**  
  - **不要**在此处加 `WAIT_*` 人闸门

#### 4b-3）开详情

- **目的**：当前岗开详情；他岗挂 `pending_details`；none 跳过
- **命令**：

```bash
python3 "$SCRAPER" \
  --position-name "<标准岗名>" \
  --city 上海 \
  --classify-input data/skillver/exports/classify_input_<岗>_<B>.json \
  --details-from-decisions data/skillver/exports/classify_decisions_<岗>_<B>.json
```

- **产出 / 成功判据**：详情 JSON / seen 更新；可选 `match_skip_*.json`、`decisions_*.json`；日志含本批新增详情
- **失败 / 人机闸门**：决策不合契约 → 修 JSON 后重跑本步；登录墙 → 回 Step 2–3

**循环控制（Agent 负责）**：

1. 累计本轮新增详情（含 4a + 各批 4b-3）
2. 若 ≥ `min-details` → 进入 Step 5
3. 若 `next_list_start_page` 有值 → `B+=1`，`N=next_list_start_page`，继续 4b-1
4. 否则 → 进入 Step 5（列表耗尽）

### Step 5：导出 CSV

- **目的**：把 `pending_export` 详情写成 Skillver CSV
- **命令**：

```bash
python3 "$EXPORT" \
  --details data/skillver/details/boss_details_<岗名>.json \
  --position-name "<标准岗名>" \
  --city 上海 \
  --dry-run
# 确认计数合理后去掉 --dry-run
```

- **产出 / 成功判据**：`data/skillver/exports/job_YYYYMMDD.csv`；正式跑会更新 seen（`exported=true`）
- **失败 / 人机闸门**：大量 `empty_city` → 检查详情 `location` 或补 `--city`；`salary_unparsed` 含日薪等非社招格式属预期跳过

### Step 6：USCC（Agent 网络检索）

- **目的**：补全空缺统一社会信用代码与工商全称
- **命令**：无爬虫脚本；网络检索 + 写文件
- **产出 / 成功判据**：
  1. 列出 CSV 中空 USCC 的不重复 `招聘品牌名`
  2. 检索候选 `uscc` / `legal_name`；歧义标 `NEEDS_HUMAN`
  3. **`WAIT_USCC_REVIEW`** — 等用户确认
  4. 写入 `data/skillver/company_uscc_cache.json`（`by_brand` + `by_uscc`；brand key 与 CSV **一字不差**）
  5. **原地修改**已有 `job_YYYYMMDD.csv` 回填（不要另存新文件；不要指望再 export 重写已 `exported=true` 的行）
- **失败 / 人机闸门**：禁止企查查/Selenium 批量爬；无公开结果 → 留空并注明

### Step 7：交付核验

- **目的**：用户确认最终 CSV 可交付
- **命令**：无
- **产出 / 成功判据**：给出 CSV **绝对路径**
- **失败 / 人机闸门**：**`WAIT_CSV_REVIEW`** — 等用户回复「CSV 已核验」前，**不宣布任务完成**

---

## 按企业采集（YATN，并行路径）

与标准岗主路径独立。默认跑 `companies.csv` 中 **S+A 全量**；不按岗位 base 城过滤；**丢掉日薪**。  
顺序强制：**列表 → Agent 分流（无 JD）→ 仅录取岗开详情 → 导出**。  
Agent 输出 `score` + 最佳标准岗；仅 **`score > 70`** 且非 null 开详情。宁缺毋滥（误杀可多，误放不允许）。契约见 `$REF_COMPANY`。

```bash
# 0) 登录
python3 "$SCRAPER" --check --cdp-port 9222

# 1) 列表（多关键词/企业；可加 --brand MiniMax 试跑）
python3 "$COMPANY" --scrape-list --priority S,A --pages 2 \
  --jobs-output data/yatn/jobs/company_jobs.json

# 2) 写 Agent 匹配输入（基于列表）→ 按 $REF_COMPANY 写 scores
python3 "$COMPANY" --write-match-input \
  --jobs-output data/yatn/jobs/company_jobs.json \
  --match-input data/yatn/exports/match_input.json

# 3) 应用分数 → 录取列表
python3 "$COMPANY" \
  --jobs-output data/yatn/jobs/company_jobs.json \
  --match-input data/yatn/exports/match_input.json \
  --apply-scores data/yatn/exports/match_scores.json \
  --accepted-output data/yatn/jobs/company_accepted.json

# 4) 仅对录取岗开详情
python3 "$COMPANY" --scrape-details \
  --jobs-output data/yatn/jobs/company_accepted.json \
  --details-output data/yatn/details/company_details.json

# 5) 导出 CSV
python3 "$COMPANY" \
  --details-output data/yatn/details/company_details.json \
  --export-csv data/yatn/exports/company_jobs.csv
```

---

## 方法选择矩阵

| 场景 | 首选 | 禁止 |
|------|------|------|
| 按标准岗抓市场 | `boss_cdp_raw.py` 分步三选一 | 一条命令指望脚本内 LLM |
| 按企业抓在招岗 | `scrape_company_jobs.py` | 混进标准岗循环硬改 |
| 标准岗归类 | Agent + `classify-decisions.md` | DeepSeek `.env` |
| 企业岗打分 | Agent + `company-job-match.md`（列表先分流；score>70） | 先全量开详情；脚本内瞎填分数 |
| 补 USCC | Agent 检索 + 人审 + 原地改 CSV | 企查查批量爬 |
| 日薪 `元/天` | 跳过 | 硬改薪资解析 |

## 安装（Agent Skill 目录）

```bash
SKILL_ROOT=~/.hermes/skills/data-science/skillver-job-scraper
mkdir -p "$SKILL_ROOT/scripts" "$SKILL_ROOT/data/skillver" "$SKILL_ROOT/references"
cp SKILL.md "$SKILL_ROOT/"
cp requirements.txt "$SKILL_ROOT/"
mkdir -p "$SKILL_ROOT/data/yatn"
cp scripts/boss_cdp_raw.py scripts/export_skillver_csv.py scripts/scrape_company_jobs.py "$SKILL_ROOT/scripts/"
cp data/city_codes.json "$SKILL_ROOT/data/"
cp data/skillver/position_catalog.json "$SKILL_ROOT/data/skillver/"
cp data/yatn/companies.csv "$SKILL_ROOT/data/yatn/"
cp references/classify-decisions.md references/company-job-match.md "$SKILL_ROOT/references/"
```

工作数据仍落在用户工作区 `data/skillver/` 与 `data/yatn/`（jobs/details/exports），勿打进 skill 包。  
Skill 包**必须**含 `references/` + `requirements.txt`。

## 最佳实践提示词

```text
使用 Skillver 职位采集 skill：
1. --check；不通则 --setup-chrome，等我「已登录」
2. --drain-inventory（带 --city）
3. 循环：--list-only → 按 references/classify-decisions.md 用内置模型写 decisions（最多 3 次）→ --details-from-decisions；直到 min-details 或无新列表
4. export 先 --dry-run 再正式（建议 --city 作回退）
5. 空 USCC 网络检索，等我确认后写 cache 并原地改 CSV
6. 等我「CSV 已核验」再结束
```

## 不要遗漏

1. `--min-details` = 本轮新增目标；默认 5、最大 50；Agent 循环，脚本不自动循环
2. 标准岗分步三选一；归类契约见 `references/classify-decisions.md`
3. 人机闸门只有登录 / USCC / CSV 三处
4. cache brand key 必须与 CSV `招聘品牌名` 一致；USCC 后**原地改 CSV**
5. 限流/验证码：停止并提示用户
6. 不要把分析摘要、企查查、脚本内 DeepSeek 加回最小集
