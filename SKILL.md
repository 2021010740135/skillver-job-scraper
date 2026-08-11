---
name: boss-zhipin-skillver
description: >
  通过本机已登录 Chrome（CDP）抓取 BOSS直聘标准岗职位，由 Agent 内置模型做标准岗归类，
  导出 Skillver job_YYYYMMDD.csv，并用 Agent 网络检索补全统一社会信用代码与工商全称。
  用户提到 BOSS直聘、zhipin、标准岗、--position-name、Skillver 导出、
  USCC、统一社会信用代码、工商全称、企业信用代码、公司主体补全，
  或要从详情导出招聘 CSV 时，应优先使用本 skill；即使未点名 skill 名，
  只要任务属于该流水线也应触发。本 skill 必须人机协同：登录 BOSS、
  核验 USCC 歧义主体、核验最终 CSV。禁止用企查查/Selenium 批量爬工商；
  禁止在脚本内再调 DeepSeek 或其它 API 做归类。
version: 2.5.0
author: eatmoreduck
license: MIT
platforms: [macos, linux, windows]
metadata:
  hermes:
    tags: [scraper, jobs, career, cdp, chrome, zhipin, boss直聘, skillver, uscc]
---

# boss-zhipin-skillver

面向 Hermes / WorkBuddy / Claude Code 等 Agent 的 **BOSS直聘 → Skillver CSV** 执行手册（最小稳定集）。

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
3. **标准岗唯一主路径** — 必须 `--position-name`（catalog 原名）  
4. **归类只用 Agent 内置模型** — 按 `references/classify-decisions.md` 写决策 JSON  
5. **人机闸门** — `WAIT_LOGIN` / `WAIT_USCC_REVIEW` / `WAIT_CSV_REVIEW`（归类后**不要**加人闸门，直接开详情）  
6. **稳优先于快** — 详情间隔保持默认  

## 前置条件

- Python >=3.10，`pip install -r requirements.txt`（`requests` + `websocket-client`）  
- 本机 Chrome；Agent 能连 `127.0.0.1:9222`  
- **不需要** `.env` / DeepSeek  

## Scripts guide

```bash
SCRAPER=scripts/boss_cdp_raw.py
EXPORT=scripts/export_skillver_csv.py
REF=references/classify-decisions.md
```

| 资源 | 用途 |
|------|------|
| `scripts/boss_cdp_raw.py` | CDP：`--drain-inventory` / `--list-only` / `--details-from-decisions` |
| `scripts/export_skillver_csv.py` | 详情 → CSV + seen |
| `references/classify-decisions.md` | Agent 归类 JSON 契约（必读） |
| `data/city_codes.json` | 城市码 |
| `data/skillver/position_catalog.json` | 58 标准岗 |

`--min-details`：默认 **5**（测速），上限 **50**（超限压到 50 并提示）。由 Agent **循环**控制是否继续抓列表，单次脚本调用不自动循环。

## 工作流

### Step 1：识别目标

确认：`position_name`、城市/筛选、`--min-details`（默认 5）、是否只要导出/补 USCC。

### Step 2–3：环境与登录

```bash
python3 "$SCRAPER" --check --cdp-port 9222
# 不通则：
python3 "$SCRAPER" --setup-chrome --cdp-port 9222
```

进入 **`WAIT_LOGIN`**，等用户回复「已登录」后再 `--check`。

### Step 4a：清当前岗库存

```bash
python3 "$SCRAPER" --position-name "<标准岗名>" --drain-inventory
```

不经 Agent 归类。若本轮新增详情已 ≥ `min-details`，可跳到 Step 5。

### Step 4b：按批循环（直到够数或无新列表）

对每一批：

**1) 列表**

```bash
python3 "$SCRAPER" \
  --position-name "<标准岗名>" \
  --city <城市> \
  --list-only \
  --list-start-page <N> \
  --page-batch-size 2 \
  --batch-index <B> \
  --pages 8 \
  --min-details <目标>
```

产出：`data/skillver/exports/classify_input_<岗>_<B>.json`  
记下输出中的 `next_list_start_page`。

**2) Agent 归类（内置模型）**

- 必读 `references/classify-decisions.md`  
- 写出 `data/skillver/exports/classify_decisions_<岗>_<B>.json`  
- 自检契约；失败最多重试 **3** 次  
- 仍失败 → **打断点**，提示用户：「归类失败，修好后回复继续」；**不开详情、不用规则顶替归类**  
- 用户回复「继续」后从本批决策或下一批续跑  

**3) 开详情**

```bash
python3 "$SCRAPER" \
  --position-name "<标准岗名>" \
  --classify-input data/skillver/exports/classify_input_<岗>_<B>.json \
  --details-from-decisions data/skillver/exports/classify_decisions_<岗>_<B>.json
```

当前岗开详情；他岗挂库存。然后检查本轮新增详情是否 ≥ `min-details`；未够且 `next_list_start_page` 有值则继续下一批。

### Step 5：导出 CSV

```bash
python3 "$EXPORT" \
  --details data/skillver/details/boss_details_<岗名>.json \
  --position-name "<标准岗名>" \
  --dry-run
# 确认后去掉 --dry-run
```

默认：`data/skillver/exports/job_YYYYMMDD.csv`。

### Step 6：USCC（Agent 网络检索）

1. 列出 CSV 中空 USCC 的不重复 `招聘品牌名`  
2. 网络检索候选 → 歧义标 `NEEDS_HUMAN`  
3. **`WAIT_USCC_REVIEW`**  
4. 写入 `company_uscc_cache.json`（brand key 与 CSV 一字不差）  
5. **原地修改**已有 `job_YYYYMMDD.csv` 回填（不要另存新文件；不要指望再 export 重写已 `exported=true` 的行）  

### Step 7：交付核验

**`WAIT_CSV_REVIEW`**：给出 CSV 绝对路径，等用户回复「CSV 已核验」。

## 方法选择矩阵

| 场景 | 首选 | 禁止 |
|------|------|------|
| 抓 BOSS | `boss_cdp_raw.py` 分步模式 | 一条命令指望脚本内 LLM |
| 标准岗归类 | Agent 内置模型 + `references/` | DeepSeek `.env`、脚本 HTTP 调模型 |
| 猎头/匿名 | 脚本规则（已在 list-only 过滤） | 交给模型浪费轮次 |
| 补 USCC | Agent 检索 + 人审 + 原地改 CSV | 企查查批量爬 |
| 归类失败 | 重试 3 次 → 打断点续跑 | 规则瞎猜开详情 |

## 安装（Agent Skill 目录）

```bash
SKILL_ROOT=~/.hermes/skills/data-science/boss-zhipin-scraper
mkdir -p "$SKILL_ROOT/scripts" "$SKILL_ROOT/data/skillver" "$SKILL_ROOT/references"
cp SKILL.md "$SKILL_ROOT/"
cp requirements.txt "$SKILL_ROOT/"
cp scripts/boss_cdp_raw.py scripts/export_skillver_csv.py "$SKILL_ROOT/scripts/"
cp data/city_codes.json "$SKILL_ROOT/data/"
cp data/skillver/position_catalog.json "$SKILL_ROOT/data/skillver/"
cp references/classify-decisions.md "$SKILL_ROOT/references/"
```

工作数据仍落在用户工作区 `data/skillver/`（jobs/details/seen/exports/cache），勿打进 skill 包。

## 最佳实践提示词

```text
使用 boss-zhipin-skillver：
1. --check；不通则 --setup-chrome，等我「已登录」
2. --drain-inventory
3. 循环：--list-only → 按 references/classify-decisions.md 用内置模型写 decisions（最多 3 次）→ --details-from-decisions；直到 min-details 或无新列表
4. export 先 dry-run 再正式
5. 空 USCC 网络检索，等我确认后写 cache 并原地改 CSV
6. 等我「CSV 已核验」再结束
```

## 不要遗漏

1. `--min-details` 是本轮新增目标；默认 5、最大 50  
2. 归类契约见 `references/classify-decisions.md`  
3. cache brand key 必须与 CSV `招聘品牌名` 一致  
4. 限流/验证码：停止并提示用户  
5. 不要把分析摘要、企查查、脚本内 DeepSeek 加回最小集  
