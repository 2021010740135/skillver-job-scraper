# Skillver 职位采集 · Agent Skill v2.18.0

![Python](https://img.shields.io/badge/python-3.10+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![Platform](https://img.shields.io/badge/platform-Windows-lightgrey.svg)
![Version](https://img.shields.io/badge/version-2.18.0-orange.svg)

通过本机已登录浏览器（Windows 优先 Edge，其次 Chrome；CDP）按 **Skillver 标准岗**分步采集公开职位，由 **Agent 内置模型**归类，导出 CSV。

面向 **WorkBuddy / Hermes / Claude Code 等任意 Agent**（见 [`SKILL.md`](./SKILL.md)），也可纯命令行。当前数据源为 **BOSS直聘**。当前只支持 **Windows**。

> **一句话**：本机浏览器 → 列表 → 清洗 A → Agent 归类 → 详情 → 清洗 B → Skillver CSV。

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
git clone https://github.com/2021010740135/skillver-job-scraper.git
cd skillver-job-scraper
python3 scripts/chrome_cdp.py --check --cdp-port 9222
python3 scripts/chrome_cdp.py --setup-chrome

python3 scripts/scrape_list.py \
  --query "阶跃星辰" --city 上海 \
  --list-start-page 1 --page-batch-size 1 --batch-index 1
python3 scripts/clean_classify_input.py \
  --input data/阶跃星辰/list_batch_1.json \
  --output data/阶跃星辰/classify_input_1.json
# Agent 按 references/classify-decisions.md 写出 decisions 后：
python3 scripts/scrape_details.py \
  --query "阶跃星辰" --city 上海 \
  --classify-input data/阶跃星辰/classify_input_1.json \
  --details-from-decisions data/阶跃星辰/classify_decisions_1.json
python3 scripts/clean_details.py --input data/阶跃星辰/details.json
python3 scripts/export_skillver_csv.py \
  --details data/阶跃星辰/details.json \
  --query "阶跃星辰" --city 上海 --dry-run
```

Agent 完整人机流程见 [`SKILL.md`](./SKILL.md)。  
归类契约见 [`references/classify-decisions.md`](./references/classify-decisions.md)。

---

## 特性

- **拆开的 CLI**：浏览器 / 列表 / 清洗 A / 详情 / 清洗 B / 导出，各司一职
- **Agent Skill 友好**：闸门清晰（登录 / CSV）；不依赖脚本内 DeepSeek / `.env`
- **自由搜索 + 58 岗映射**：`--query` 进搜索框；对上 catalog 任一标准岗即开详情
- **明文薪资**：页面内 API（BOSS），默认不走易被字体反爬干扰的 DOM
- **隔离浏览器 profile**：不碰主浏览器；Windows 优先 Edge，没有再用 Chrome

### 为什么用 CDP，而不是 Selenium / Playwright？

受控自动化浏览器体积大、指纹明显，更容易触发招聘站风控。本工具连接**你已登录的真实浏览器**，复用真实会话与指纹，调用页面内搜索接口拿明文薪资，比纯 DOM 爬更稳、也更克制。

---

## 安装

### A. 作为 Agent Skill

Agent 按 [`references/install.md`](./references/install.md) 把文件拷到本机 skills 目录，再跑 `--check`。不要另写安装脚本。

Skill 包须含：`SKILL.md`、`pyproject.toml`、`uv.lock`、`scripts/`（含 `ensure_uv_env.py`）、`references/`、`data/city_codes.json`、`data/position_catalog.json`。  
工作数据落在用户工作区 `data/<搜索词>/`，不要打进 skill 包。

### B. 仅命令行

```bash
python3 scripts/chrome_cdp.py --check
python3 scripts/chrome_cdp.py --setup-chrome
```

`--check` 会：查找 uv → 没有则安装 → `uv sync` 到项目 `.venv` → 查 CDP → 查登录。国内可设 `UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple`。不要把依赖 pip 进系统 Python。

---

## Skillver 流水线

```text
chrome_cdp --setup-chrome / --check
→ scrape_list → jobs.json + list_batch_N.json
→ clean_classify_input → classify_input_N.json
→ Agent 按 classify-decisions.md 写 decisions
→ scrape_details --details-from-decisions（从 jobs.json 取 URL）
→ clean_details → slim details.json
→ export_skillver_csv → 用户核验 CSV
```

### 核心约定

1. `--query` 随便定；归类结果的 `position_name` 只能是 catalog 原名或 `null`。
2. 归类由 **Agent 内置模型**完成；脚本内不再调外部 LLM API。
3. `--min-details` = 停翻页的最低映射数（默认 5，上限 50）。够了就停翻；最后一页多出来的详情全开。站点不够可以少于目标。
4. 全局 `data/seen_jobs.json` 按 `encrypt_job_id` 去重。已爬详情但未进 CSV 的 id 记在 `data/unexported_details.json`，导出成功后去掉。
5. 清洗只丢多余字段，不因实习 / 日薪丢卡片；导出仍跳过无法解析的日薪。
6. `security_id` / `lid` 留在 `jobs.json`，不进 classify_input。
7. 禁止企查查 / Selenium 批量爬工商。

---

## 文件结构

```
├── SKILL.md                         # 导航（When / How / What）
├── README.md
├── CHANGELOG.md
├── references/
│   ├── install.md
│   ├── chrome-setup.md
│   ├── scrape-list.md
│   ├── clean-classify-input.md
│   ├── classify-decisions.md
│   ├── scrape-details.md
│   ├── clean-details.md
│   └── export-csv.md
├── data/
│   ├── city_codes.json
│   ├── position_catalog.json
│   ├── seen_jobs.json              # 运行时：id 去重
│   └── unexported_details.json     # 运行时：已爬详情未进 CSV
├── scripts/
│   ├── chrome_cdp.py
│   ├── scrape_list.py
│   ├── scrape_details.py
│   ├── clean_classify_input.py
│   ├── clean_details.py
│   ├── export_skillver_csv.py
│   ├── boss_common.py               # 共享运行时（非 CLI）
│   ├── job_schema.py
│   └── ensure_uv_env.py
└── tests/
```

---

## 浏览器 profile

`--setup-chrome` 使用持久隔离目录（默认 `~/.boss-zhipin-scraper/chrome-profile`），**默认不复制**主浏览器。Windows 先启动 Edge，没有再用 Chrome。不用时：

```bash
python3 scripts/chrome_cdp.py --stop-chrome
```

仅按隔离 profile 匹配进程，不误杀主浏览器。

---

## 许可

MIT。使用前请阅读本文顶部的**免责声明**。
