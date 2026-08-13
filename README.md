# Skillver 职位采集 · Agent Skill v2.10.0

![Python](https://img.shields.io/badge/python-3.10+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Linux%20%7C%20Windows-lightgrey.svg)
![Version](https://img.shields.io/badge/version-2.10.0-orange.svg)

通过**本机已登录**的 Chrome / Edge（CDP 调试端口）采集公开职位，由 **Agent 内置模型**归类/打分，导出 Skillver CSV。面向 WorkBuddy / Hermes / Claude Code 等任意 Agent，也可纯命令行。当前数据源为 **BOSS直聘**。

> 一句话：**本机浏览器 →（标准岗 或 按企业）→ Agent 归类/打分 → CSV**

---

## ✨ 特性

- 🤖 **Agent Skill 友好** — 闸门清晰（登录 / CSV 核验），不依赖脚本内 LLM / `.env`
- 🎯 **58 标准岗 + 定岗规则表** — `position_aliases.json` 170 条别名，先规则后语义，歧义人工确认回写
- 🔄 **断点续爬** — `task_state_<岗>.json` 自动记录进度，中断重启自动续爬
- 💾 **落盘不丢数据** — 列表每页写、详情每条写、seen 每条更新
- 🧩 **分步可控** — 标准岗 drain / list-only / details-from-decisions；企业路径 list → details → match → export
- 🌐 **隔离浏览器 profile** — 不碰主浏览器；Chrome / Edge 自适应；macOS / Linux / Windows
- 📊 **明文薪资** — 走页面内 API，避开字体反爬；规范为 `N K-M K`

---

## ⚠️ 免责声明

本项目仅供**个人求职分析、学习与技术研究**。使用者须自行遵守目标网站用户协议及适用法律法规，不得用于商业转售、恶意批量抓取或对目标站点造成不合理负担。

- 请使用**本人已登录**的浏览器会话；不要分享 Cookie / 专用 profile
- 抓取节奏保持脚本默认间隔；遇验证码、限流或风控应立即停止并人工处理
- **使用本软件所产生的一切后果由使用者自行承担**；维护者不就滥用、封号、数据争议或合规风险承担义务

涉及 BOSS直聘时，请同时阅读其 [用户协议](https://www.zhipin.com/about/protocol.html)。

---

## 快速开始

```bash
# 1. 克隆 + 装依赖（或 uv sync）
git clone https://github.com/2021010740135/skillver-job-scraper.git
cd skillver-job-scraper
pip install -r requirements.txt

# 2. 启动隔离浏览器并登录（登录态持久，仅首次需在弹出窗口登录）
python3 scripts/boss_cdp_raw.py --setup-chrome
python3 scripts/boss_cdp_raw.py --check            # 验证 CDP + 登录态

# 3. 标准岗分步循环（岗位名必须是 catalog 原名）
python3 scripts/boss_cdp_raw.py \
  --position-name "Agent工程师" --city 上海 --drain-inventory
python3 scripts/boss_cdp_raw.py \
  --position-name "Agent工程师" --city 上海 \
  --list-only --list-start-page 1 --page-batch-size 2 --batch-index 1

# 4. Agent 按 references/classify-decisions.md 写出 decisions 后开详情
python3 scripts/boss_cdp_raw.py \
  --position-name "Agent工程师" --city 上海 \
  --classify-input data/skillver/exports/classify_input_Agent工程师_1.json \
  --details-from-decisions data/skillver/exports/classify_decisions_Agent工程师_1.json

# 5. 导出 Skillver CSV（先 --dry-run 核对计数）
python3 scripts/export_skillver_csv.py \
  --details data/skillver/details/boss_details_Agent工程师.json \
  --position-name "Agent工程师" --city 上海 --dry-run
```

作为 Agent Skill 安装时，权威契约见 [`start.md`](./start.md)（含安全审计、uv 托管解释器、venv 依赖、`--check` 验证）。完整人机流程与 Step 循环见 [`SKILL.md`](./SKILL.md)。

---

## 两种采集路径

| | 标准岗（主路径） | 按企业（YATN） |
|---|---|---|
| **输入** | 用户描述 → 58 标准岗 | 企业名单 `data/yatn/companies.csv` |
| **归类/打分** | Agent 按 `classify-decisions.md` 归类 | Agent 按 `company-job-match.md` 打分，`score > 70` 才开详情 |
| **输出** | Skillver `job_YYYYMMDD.csv` | 后端 `company_jobs.csv` |
| **详情过滤** | 猎头/匿名规则 + Agent 归类 | 列表先分流（无 JD 直接丢），宁缺毋滥 |

---

## 标准岗采集（主路径）

### 完整循环

```text
Step 0  安装 skill（start.md 权威契约）
Step 1  识别目标：定岗（见下文）→ 确认城市 / min-details
Step 2  --drain-inventory         清当前岗 pending 库存（不经归类直接补详情）
Step 3  循环（直到新增详情 ≥ min-details 或无新列表）：
        --list-only              一批列表 → classify_input（猎头/匿名规则过滤）
        → Agent 写 decisions     按 references/classify-decisions.md（最多 3 次）
        → --details-from-decisions 开详情（当前岗 / 他岗挂库存 / none）
Step 4  export_skillver_csv      先 --dry-run 再正式（建议 --city 作回退）
Step 5  交付核验                 Agent 给 CSV 路径，等用户「CSV 已核验」
```

三个分步模式互斥，单次调用只选一个；`--min-details` = **本轮新增**目标（默认 5、上限 50），循环由 Agent 编排，脚本不自动循环。

### 断点续爬

- 每个岗位一个 `data/skillver/task_state_<岗名>.json`，由脚本在 drain / list-only / details-from-decisions **每次结束时自动写**（阶段、批次、下一批页码、本轮新增详情数）
- 任何标准岗命令启动时**自动检测**上次状态并打印续爬提示（按是否达标给出建议）
- 落盘保证：**列表每页写、详情每条写、seen 每条更新**——中断不丢已抓数据，重启后重跑同一条命令即按 seen 跳过已抓，只补剩余

### 定岗：用户叫法 → 58 标准岗

用户用自然语言描述岗位时，按 `data/skillver/position_aliases.json`（58 岗全覆盖、170 条别名）做规则匹配：

1. **唯一命中** → 直接取 catalog 原名
2. **消歧优先最长别名** — 多候选时若某命中别名是另一命中别名的严格超串（如「具身智能研究」⊃「具身智能」），淘汰较短者
3. **仍多候选** → 列出候选，**用户手动确认**，选择回写规则表（下次同输入直接命中）
4. **零命中** → Agent 内置模型语义映射

脚本侧 `resolve_position` 仍**严格校验** catalog 原名，不合法直接拒绝——规则层只决定「传什么岗名」。

### 参数速查

| 参数 | 说明 |
|---|---|
| `--position-name` | **必填**，catalog 原名，同时作搜索词 |
| `--city` | 城市中文名或代码（默认上海），建议始终带上 |
| `--drain-inventory` | 补抓当前岗 `pending_details` |
| `--list-only` | 一批列表 → `classify_input` |
| `--list-start-page` / `--page-batch-size` / `--batch-index` | 默认 1 / 2 / 1 |
| `--pages` | 搜索页硬上限（默认 8） |
| `--min-details` | 本轮目标**新增**详情数（默认 5，上限 50） |
| `--classify-input` + `--details-from-decisions` | 按 Agent 决策开详情 |
| `--match-report` / `--decision-report` | 跳过 / 决策报告（有默认路径） |
| `--cdp-port` | CDP 调试端口（默认 9222） |
| `--setup-chrome` / `--check` / `--stop-chrome` | 环境、验证、收尾 |
| `--experience` / `--scale` 等 | 筛选；支持逗号或重复多选 |

导出脚本常用：`--details`、`--position-name`、`--city`（空 location 回退）、`--dry-run`、`--append`。

---

## 按企业采集（YATN）

```bash
# 1) 列表（S+A 全量；多关键词 = 全称/品牌/别名召回）
python3 scripts/scrape_company_jobs.py --scrape-list --priority S,A --pages 2 \
  --jobs-output data/yatn/jobs/company_jobs.json

# 2) 生成匹配输入，Agent 按 references/company-job-match.md 打分
python3 scripts/scrape_company_jobs.py --write-match-input \
  --jobs-output data/yatn/jobs/company_jobs.json \
  --match-input data/yatn/exports/match_input.json
python3 scripts/scrape_company_jobs.py \
  --jobs-output data/yatn/jobs/company_jobs.json \
  --match-input data/yatn/exports/match_input.json \
  --apply-scores data/yatn/exports/match_scores.json \
  --accepted-output data/yatn/jobs/company_accepted.json

# 3) 仅对 score>70 的录取岗开详情 → 导出
python3 scripts/scrape_company_jobs.py --scrape-details \
  --jobs-output data/yatn/jobs/company_accepted.json \
  --details-output data/yatn/details/company_details.json
python3 scripts/scrape_company_jobs.py \
  --details-output data/yatn/details/company_details.json \
  --export-csv data/yatn/exports/company_jobs.csv
```

规则：S+A 全量、不按 base 城过滤、丢日薪、列表先分流、`score > 70` 才开详情/导出。

---

## 导出 CSV

8 列结构：

| 列 | 说明 |
|---|---|
| `招聘品牌名` | BOSS 招聘品牌名 |
| `所在城市` | 提取的城市名（城市码前缀匹配，如「上海青浦区…」→ 上海） |
| `一级编号` | catalog 意图族 ID（J01-J11 / J99） |
| `一级岗位名称` | 意图族标签（12 个，粗分类） |
| `岗位名称` | 58 标准岗原名（细分类） |
| `岗位描述` | JD 全文（逗号转全角，免引号） |
| `岗位base地` | 完整办公地址（location 原值） |
| `岗位薪资` | 规范为 `N K-M K`；日薪/面议等无法规范的行直接跳过 |

岗位名三列（一级编号 / 一级岗位名称 / 岗位名称）均来自 catalog，**禁止**用招聘站 title 冒充。

---

## 核心约定

1. 正式 `position_name` 只能是 catalog 原名；CSV 岗名三列来自 catalog
2. 归类由 **Agent 内置模型**完成；脚本内不再调外部 LLM API
3. 定岗先规则后语义：唯一命中直接定岗；歧义人工确认并回写规则表；零命中才语义映射
4. `--min-details` = 本轮新增目标，不是历史累计；单次脚本调用不自动循环
5. `seen_jobs.json`（v2）：`jobs` 为真相表；`pending_details` / `pending_export` 为待办索引
6. 详情应带 `location`；导出无 `--city` 也可出城，旧空 location 建议传 `--city`
7. 社招主路径不处理日薪（`元/天`）等无法规范为 `NK-MK` 的薪资
8. 抓取流程人机闸门只有**登录 / CSV 核验**两处；定岗歧义确认属任务开始前的前置交互

---

## 文件结构

```
├── SKILL.md                    # Agent 执行手册（主入口）
├── README.md
├── CHANGELOG.md
├── start.md                    # 安装契约（权威）
├── LICENSE                     # MIT
├── pyproject.toml / requirements.txt
├── references/
│   ├── classify-decisions.md   # 标准岗归类契约
│   └── company-job-match.md    # 企业岗 score 契约
├── data/
│   ├── city_codes.json
│   ├── skillver/position_catalog.json    # 58 标准岗（可提交）
│   ├── skillver/position_aliases.json    # 定岗规则表 170 别名（可提交）
│   └── yatn/companies.csv                # YATN 企业名单（可提交）
├── scripts/
│   ├── boss_cdp_raw.py         # 标准岗 CDP CLI
│   ├── export_skillver_csv.py  # 标准岗 → Skillver CSV
│   └── scrape_company_jobs.py  # 按企业采集 → 后端 CSV
└── tests/
```

工作数据（`seen_jobs.json`、`task_state_*.json`、`jobs/`、`details/`、`exports/`）落在**用户工作区**，不入库、不进 skill 包。

---

## 常见问题

**爬一半停了，之前抓到的会丢吗？** 不会。列表每页落盘、详情每条落盘、seen 每条更新；配合 `task_state` 断点续爬，重启后自动提示从断点继续。

**用户描述和 58 岗对不上怎么办？** 规则表唯一命中直接定岗；歧义列候选人工确认（并回写规则表）；零命中由 Agent 语义映射。

**为什么用 CDP 而不是 Selenium / Playwright？** 受控自动化浏览器体积大、指纹明显，更容易触发风控。本工具连接你已登录的真实浏览器，复用真实会话与指纹，调用页面内搜索接口拿明文薪资，更稳也更克制。

**支持哪些浏览器？** CDP 协议兼容 Chrome / Edge（实测 Edge 可用），`--setup-chrome` 按平台自动探测（Chrome 优先、Edge 兜底）。Firefox / Safari 不支持。

---

## 许可

MIT。使用前请阅读本文顶部的**免责声明**。
