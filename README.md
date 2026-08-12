# Skillver 职位采集 · Agent Skill v2.6.0

![Python](https://img.shields.io/badge/python-3.10+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Linux%20%7C%20Windows-lightgrey.svg)
![Version](https://img.shields.io/badge/version-2.6.0-orange.svg)

通过本机已登录 Chrome（CDP）采集公开职位：① **Skillver 标准岗**分步流水线；② **按企业名单**召回在招岗（YATN）。均由 **Agent 内置模型**归类/打分，导出 CSV，标准岗路径还可补全 USCC / 工商全称。

面向 **WorkBuddy / Hermes / Claude Code 等任意 Agent**（见 [`SKILL.md`](./SKILL.md)），也可纯命令行。当前数据源为 **BOSS直聘**。

> **一句话**：本机 Chrome →（标准岗 **或** 按企业）→ Agent 归类/打分 → CSV。

---

## 免责声明

本项目仅供个人求职分析、学习与技术研究。使用者须自行遵守目标网站用户协议及适用法律法规，不得用于商业转售、恶意批量抓取或对目标站点造成不合理负担。

- 请使用**本人已登录**的浏览器会话；不要分享 Cookie / 专用 profile。
- 抓取节奏保持脚本默认间隔；遇验证码、限流或风控应立即停止并人工处理。
- **使用本软件所产生的一切后果由使用者自行承担**；维护者不就滥用、封号、数据争议或合规风险承担义务。

涉及 BOSS直聘时，请同时阅读其 [用户协议](https://www.zhipin.com/about/protocol.html)。

---

## 30 秒快速开始

```bash
# 1. 克隆 + 依赖
git clone https://github.com/2021010740135/skillver-job-scraper.git
cd skillver-job-scraper
pip install -r requirements.txt          # 或 uv sync

# 2. 启动隔离 Chrome 并登录（登录态持久；首次在弹出窗口登录）
python3 scripts/boss_cdp_raw.py --setup-chrome

# 3. 标准岗分步（必须 --position-name；完整循环见 SKILL.md）
python3 scripts/boss_cdp_raw.py \
  --position-name "Agent工程师" --city 上海 --drain-inventory
python3 scripts/boss_cdp_raw.py \
  --position-name "Agent工程师" --city 上海 \
  --list-only --list-start-page 1 --page-batch-size 2 --batch-index 1
# Agent 按 references/classify-decisions.md 写出 decisions 后：
python3 scripts/boss_cdp_raw.py \
  --position-name "Agent工程师" --city 上海 \
  --classify-input data/skillver/exports/classify_input_Agent工程师_1.json \
  --details-from-decisions data/skillver/exports/classify_decisions_Agent工程师_1.json

# 4. 导出 Skillver CSV（建议先 --dry-run）
python3 scripts/export_skillver_csv.py \
  --details data/skillver/details/boss_details_Agent工程师.json \
  --position-name "Agent工程师" \
  --city 上海 \
  --dry-run
```

Agent 完整人机流程（登录 / USCC / CSV 核验）见 [`SKILL.md`](./SKILL.md)。  
归类契约见 [`references/classify-decisions.md`](./references/classify-decisions.md)。

---

## 特性

- **Agent Skill 友好**：闸门清晰（登录 / USCC / CSV）；不依赖脚本内 DeepSeek / `.env`
- **标准岗主路径**：`--position-name` + `position_catalog.json`（58 岗）
- **按企业采集（YATN）**：`data/yatn/companies.csv` + `scripts/scrape_company_jobs.py`；多别名召回；列表先分流；Agent `score>70` + 标准岗后再开详情；导出后端 CSV
- **分步可控**：标准岗 drain / list-only / details-from-decisions；企业路径 list → details → match → export
- **明文薪资**：页面内 API（BOSS），默认不走易被字体反爬干扰的 DOM
- **导出**：Skillver `job_YYYYMMDD.csv` 或企业岗 CSV；USCC 人审回填（标准岗路径）
- **隔离 Chrome profile**：不碰主浏览器；macOS / Linux / Windows

### 为什么用 CDP，而不是 Selenium / Playwright？

受控自动化浏览器体积大、指纹明显，更容易触发招聘站风控。本工具连接**你已登录的真实 Chrome**，复用真实会话与指纹，调用页面内搜索接口拿明文薪资，比纯 DOM 爬更稳、也更克制。

---

## 安装

### A. 作为 Agent Skill（WorkBuddy / Hermes 等）

把最小文件集拷到你的 Agent skills 目录即可（路径按宿主调整）：

```bash
git clone https://github.com/2021010740135/skillver-job-scraper.git
cd skillver-job-scraper

SKILL_ROOT=~/.hermes/skills/data-science/skillver-job-scraper   # 示例路径
mkdir -p "$SKILL_ROOT/scripts" "$SKILL_ROOT/data/skillver" "$SKILL_ROOT/references"
cp SKILL.md requirements.txt "$SKILL_ROOT/"
cp scripts/boss_cdp_raw.py scripts/export_skillver_csv.py "$SKILL_ROOT/scripts/"
cp data/city_codes.json "$SKILL_ROOT/data/"
cp data/skillver/position_catalog.json "$SKILL_ROOT/data/skillver/"
cp references/classify-decisions.md "$SKILL_ROOT/references/"
```

Skill 包须含：`SKILL.md`、`requirements.txt`、`scripts/`、`references/`、`data/city_codes.json`、`data/skillver/position_catalog.json`。  
工作数据（jobs/details/seen/exports/cache）落在**用户工作区**，不要打进 skill 包。

对话示例：「按标准岗抓上海 Agent工程师 并导出 Skillver CSV」（须遵守 `SKILL.md` 人机闸门）。

### B. 仅命令行

```bash
git clone https://github.com/2021010740135/skillver-job-scraper.git
cd skillver-job-scraper
pip install -r requirements.txt
python3 scripts/boss_cdp_raw.py --setup-chrome
python3 scripts/boss_cdp_raw.py --check
```

可选：`pip install -e .` 后使用入口 `boss-scraper` / `boss-export-skillver`。

---

## 主路径参数（常用）

| 参数 | 说明 |
|------|------|
| `--position-name` | **必填**，catalog 原名；同时作搜索词 |
| `--city` | 城市中文名或代码（默认上海）；建议始终带上 |
| `--drain-inventory` | 清当前岗 `pending_details`（不经 Agent 归类） |
| `--list-only` | 一批列表 → `classify_input` |
| `--list-start-page` / `--page-batch-size` / `--batch-index` | 默认 1 / 2 / 1 |
| `--pages` | 搜索页硬上限（默认 8） |
| `--min-details` | 本轮目标**新增**详情数（默认 5，上限 50；Agent 循环） |
| `--classify-input` + `--details-from-decisions` | 按 Agent 决策开详情 |
| `--match-report` / `--decision-report` | 跳过/决策报告（标准岗有默认路径） |
| `--cdp-port` | 默认 9222 |
| `--setup-chrome` / `--check` / `--stop-chrome` | 环境与收尾 |
| `--experience` / `--scale` 等 | 筛选；experience/scale 支持逗号或重复多选 |

导出脚本常用：`--details`、`--position-name`、`--city`（空 location 回退）、`--dry-run`、`--append`、`--uscc-cache`。

完整说明与 Step 循环见 [`SKILL.md`](./SKILL.md)。

### 按企业采集（YATN）速查

```bash
python3 scripts/scrape_company_jobs.py --scrape-list --priority S,A --pages 2 \
  --jobs-output data/yatn/jobs/company_jobs.json
python3 scripts/scrape_company_jobs.py --write-match-input \
  --jobs-output data/yatn/jobs/company_jobs.json \
  --match-input data/yatn/exports/match_input.json
# Agent 按 references/company-job-match.md 写 match_scores 后：
python3 scripts/scrape_company_jobs.py \
  --jobs-output data/yatn/jobs/company_jobs.json \
  --match-input data/yatn/exports/match_input.json \
  --apply-scores data/yatn/exports/match_scores.json \
  --accepted-output data/yatn/jobs/company_accepted.json
python3 scripts/scrape_company_jobs.py --scrape-details \
  --jobs-output data/yatn/jobs/company_accepted.json \
  --details-output data/yatn/details/company_details.json
python3 scripts/scrape_company_jobs.py \
  --details-output data/yatn/details/company_details.json \
  --export-csv data/yatn/exports/company_jobs.csv
```

企业表：`data/yatn/companies.csv`。规则：S+A 全量、不按 base 城过滤、丢日薪、列表先分流、`score>70` 才开详情/导出。

---

## Skillver 流水线

```text
drain-inventory（清库存）
→ list-only（去重 + 猎头/匿名规则 → classify_input）
→ Agent 按 references/classify-decisions.md 写 decisions
→ details-from-decisions（当前岗详情 / 他岗库存 / none）
→ 未达 min-details 且还有下一页 → 下一批
→ export_skillver_csv → USCC 检索人审 → 原地改 CSV
```

### 核心约定

1. 正式 `position_name` 只能是 catalog 原名；CSV 岗名三列来自 catalog，禁止用招聘站 title 冒充。
2. 归类由 **Agent 内置模型**完成；脚本内不再调外部 LLM API。
3. `--min-details` = 本轮新增目标，不是历史累计；单次脚本调用不自动循环。
4. `seen_jobs.json`（v2）：`jobs` 为真相表；`pending_details` / `pending_export` 为待办索引。
5. 2.5.1 起详情应带 `location`；导出无 `--city` 也可出城；旧空 location 仍建议传 `--city`。
6. 社招主路径不处理日薪（`元/天`）等无法规范为 `NK-MK` 的薪资。
7. 禁止企查查 / Selenium 批量爬工商；USCC 靠公开检索 + 人审。

### 目录（本地产物勿提交）

```
data/skillver/
├── position_catalog.json      # 可提交：58 标准岗
├── seen_jobs.json             # 本地
├── company_uscc_cache.json    # 本地
├── jobs/  details/  exports/  # 本地
└── eval/                      # 可选
```

---

## 文件结构

```
├── SKILL.md                         # Agent 执行手册（主入口）
├── README.md
├── CHANGELOG.md
├── LICENSE
├── pyproject.toml
├── requirements.txt
├── references/
│   ├── classify-decisions.md        # 标准岗归类契约
│   └── company-job-match.md         # 企业岗 score 契约
├── data/
│   ├── city_codes.json
│   ├── skillver/position_catalog.json
│   └── yatn/companies.csv           # YATN 企业名单
├── scripts/
│   ├── boss_cdp_raw.py              # 标准岗 CDP CLI
│   ├── export_skillver_csv.py       # 标准岗 → Skillver CSV
│   └── scrape_company_jobs.py       # 按企业采集 → 后端 CSV
└── tests/
```

---

## Chrome profile

`--setup-chrome` 使用持久隔离目录（默认 `~/.boss-zhipin-scraper/chrome-profile`），**默认不复制**主 Chrome。抓取结束后默认不关浏览器；不用时：

```bash
python3 scripts/boss_cdp_raw.py --stop-chrome
```

仅按隔离 profile 匹配进程，不误杀主 Chrome。

---

## 许可

MIT。使用前请阅读本文顶部的**免责声明**。
