# Skillver 职位采集 · Agent Skill v1.0.0

![Python](https://img.shields.io/badge/python-3.10+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![Platform](https://img.shields.io/badge/platform-Windows-lightgrey.svg)
![Version](https://img.shields.io/badge/version-1.0.0-orange.svg)

通过**本机已登录**浏览器（Windows 优先 Edge，其次 Chrome；CDP）按任意搜索词采集公开职位，由 **Agent 内置模型**映射到 58 个 Skillver 标准岗，导出 CSV。面向 WorkBuddy / Hermes / Claude Code 等任意 Agent，也可纯命令行。当前数据源为 **BOSS直聘**。当前只支持 **Windows**。

> 一句话：**本机浏览器 → 列表 → 清洗 A → Agent 归类 → 详情 → 清洗 B → CSV**

---

## ✨ 特性

- 🤖 **Agent Skill 友好** — 闸门只有登录 / CSV 核验，不依赖脚本内 LLM / `.env`
- 🎯 **自由搜索 + 58 岗映射** — `--query` 进搜索框；归类对上 catalog 任一标准岗即开详情
- 📄 **按页归类、详情全开** — 每抓 1 页就映射；不够且还能翻页就继续，不设翻页上限；最后一页多出来的已映射帖全部开详情
- 💾 **落盘不丢数据** — 列表每页写、详情每条写、seen 按 id 去重；未进 CSV 的详情记在 `unexported_details.json`
- 🧩 **分步可控** — 浏览器 / 列表 / 清洗 A / 归类 / 详情 / 清洗 B / 导出，各司一职
- 🌐 **隔离浏览器 profile** — 不碰主浏览器；Windows 先 Edge，没有再用 Chrome
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
# 1. 克隆
git clone https://github.com/2021010740135/skillver-job-scraper.git
cd skillver-job-scraper

# 2. 启动隔离浏览器并登录（登录态持久，仅首次需在弹出窗口登录）
python3 scripts/chrome_cdp.py --check --cdp-port 9222
python3 scripts/chrome_cdp.py --setup-chrome

# 3. 抓 1 页列表（可按需改 --query）
python3 scripts/scrape_list.py \
  --query "阶跃星辰" --city 上海 \
  --list-start-page 1 --page-batch-size 1 --batch-index 1
python3 scripts/clean_classify_input.py \
  --input data/阶跃星辰/list_batch_1.json \
  --output data/阶跃星辰/classify_input_1.json

# 4. Agent 按 references/classify-decisions.md 写出 decisions 后开详情
python3 scripts/scrape_details.py \
  --query "阶跃星辰" --city 上海 \
  --classify-input data/阶跃星辰/classify_input_1.json \
  --details-from-decisions data/阶跃星辰/classify_decisions_1.json
python3 scripts/clean_details.py --input data/阶跃星辰/details.json

# 5. 导出 Skillver CSV（先 --dry-run 核对计数）
python3 scripts/export_skillver_csv.py \
  --details data/阶跃星辰/details.json \
  --query "阶跃星辰" --city 上海 --dry-run
```

作为 Agent Skill 安装时，按 [`references/install.md`](./references/install.md) 拷文件并跑 `--check`（uv 托管解释器、项目 `.venv`）。完整人机循环见 [`SKILL.md`](./SKILL.md)。

`--check` 会：查找 uv → 没有则安装 → `uv sync` 到项目 `.venv` → 查 CDP → 查登录。国内可设 `UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple`。不要把依赖 pip 进系统 Python。

---

## 采集循环

```text
Step 0  安装 skill（references/install.md）
Step 1  锁定 --query（任意搜索词）、城市、--min-details（停翻页的最低映射数）
Step 2  chrome_cdp --check / --setup-chrome     登录闸门
Step 3  循环（映射数不够且还有下一页则继续，不设翻页上限）：
        scrape_list（每次 1 页）→ list_batch_P.json
        → clean_classify_input → classify_input_P.json
        → Agent 写 classify_decisions_P.json（最多 3 次；失败则停、不开详情）
        → 累计 position_name != null；不够且有 next_list_start_page → P+=1
Step 4  scrape_details 一次传入全部 decisions；已映射帖全部开详情（不按 --min-details 截断）
Step 5  clean_details → export_skillver_csv（先 --dry-run）
Step 6  交付核验：给出 CSV 路径，等用户「CSV 已核验」
```

脚本不自动循环；翻页与归类由 Agent 按 [`SKILL.md`](./SKILL.md) 编排。`--min-details` 默认 5、上限 50，只决定**何时停翻页**，不是详情条数上限。站点不够可以少于目标。

### 中断了会丢数据吗

不会。列表每页落盘、详情每条落盘、`seen_jobs.json` 按 `encrypt_job_id` 更新。已开详情但还没写成 CSV 的 id 记在 `data/unexported_details.json`，下次导出自动并入，成功后去掉。重启后从 `next_list_start_page` 继续即可。

### 用户说法怎么对上 58 岗

`--query` 就是搜索框里的词，不必先是 catalog 原名。列表出来后，Agent 按 [`references/classify-decisions.md`](./references/classify-decisions.md) 把每条映射到 58 岗原名或 `null`。对上任一标准岗就开详情，不再「本轮只锁一个岗」。

定岗映射的评测约定见 [`data/eval/README.md`](./data/eval/README.md)（岗名准确率 / 误收率）；跑分脚本是 `scripts/eval_position_mapping.py`。

### 参数速查

| 参数 | 说明 |
|---|---|
| `--query` | 搜索词（任意）；`--position-name` 只是它的别名 |
| `--city` | 城市中文名或代码（默认上海），建议始终带上 |
| `--list-start-page` / `--page-batch-size` / `--batch-index` | 默认每次 1 页；`--pages` 不作硬上限 |
| `--min-details` | 停翻页的最低映射数（默认 5，上限 50） |
| `--classify-input` + `--details-from-decisions` | 按 Agent 决策开详情（可多个 decisions 文件） |
| `--cdp-port` | CDP 调试端口（默认 9222） |
| `--setup-chrome` / `--check` / `--stop-chrome` | 环境、验证、收尾 |
| `--experience` / `--scale` 等 | 筛选；支持逗号或重复多选 |

导出常用：`--details`、`--query`、`--city`（空 location 回退）、`--dry-run`、`--append`。

---

## 导出 CSV

| 列 | 说明 |
|---|---|
| `企业名称` | 招聘品牌名（与站点展示名一致） |
| `招聘品牌名` | BOSS 招聘品牌名 |
| `所在城市` | 从 location 提取的城市名 |
| `一级编号` | catalog 意图族 ID（J01–J11 / J99） |
| `一级岗位名称` | 意图族标签（粗分类） |
| `岗位名称` | 58 标准岗原名（细分类） |
| `岗位描述` | JD 全文（逗号转全角，免引号） |
| `岗位base地` | 完整办公地址（location 原值） |
| `岗位薪资` | 规范为 `N K-M K`；日薪/面议等无法规范的行直接跳过 |

岗位名三列均来自 catalog，**禁止**用招聘站 title 冒充。清洗只丢多余字段，不因实习/日薪丢卡片；导出仍跳过无法解析的日薪。

---

## 核心约定

1. `--query` 随便定；归类结果的 `position_name` 只能是 catalog 原名或 `null`
2. 归类由 **Agent 内置模型**完成；脚本内不再调外部 LLM API
3. `--min-details` = 停翻页的最低映射数，不是历史累计，也不截断最后一页详情
4. 全局 `seen_jobs.json` 只按 `encrypt_job_id` 去重；未导出详情走 `unexported_details.json`
5. 详情应带 `location`；导出无 `--city` 也可出城，旧空 location 建议传 `--city`
6. 人机闸门只有**登录 / CSV 核验**两处；归类成功后不要再加人闸门
7. 禁止企查查 / Selenium 批量爬工商

---

## 版本迭代

`1.0.0` 为当前对外最初版本。更早的 2.x 实验记录见 [`CHANGELOG.md`](./CHANGELOG.md)。

| 版本 | 增加了什么 | 贡献者 |
|---|---|---|
| **1.0.0（最初版本）** | 标准岗主路径定型：拆开的 CLI、自由搜索 `--query`、58 岗全映射、按页归类、详情全开、`seen` 只按 id、`unexported_details.json`、Windows 优先 Edge | [2021010740135](https://github.com/2021010740135) |
| 1.0.0 | 定岗映射评测约定 + `scripts/eval_position_mapping.py`；README 章节版式（特性 / 循环 / FAQ） | [aotedijia](https://github.com/aotedijia)（臭臭） |

新版本合入后在本表顶部追加一行。

---

## TODO

协作认领时改「状态」即可。

| 事项 | 说明 | 状态 |
|---|---|---|
| 城市从地址提取 | `city_from_location` 用 `city_codes.json` 最长前缀，避免「上海青浦区…」整串当地名、中间的 `·` 切错 | 待做 |
| 定岗评测金标 | `skillver_position_mapping_v1.json` 当时没进仓库；补上才能跑准确率 / 误收率 | 待做 |
| 定岗别名表 | `position_aliases.json` + 最长别名消歧，只帮 Step 1 收搜索词，**不**改回「一次只开一个岗」 | 可选 |
| 续跑提示 | 启动时打印 `next_list_start_page` / 已映射数 / 未导出条数（不恢复 drain / `task_state`） | 可选 |

---

## 文件结构

```
├── SKILL.md                         # Agent 执行手册（导航）
├── README.md
├── CHANGELOG.md
├── LICENSE
├── pyproject.toml / uv.lock
├── references/
│   ├── install.md                   # 安装契约
│   ├── chrome-setup.md
│   ├── scrape-list.md
│   ├── clean-classify-input.md
│   ├── classify-decisions.md        # 归类契约
│   ├── scrape-details.md
│   ├── clean-details.md
│   └── export-csv.md
├── data/
│   ├── city_codes.json
│   ├── position_catalog.json        # 58 标准岗（可提交）
│   ├── eval/README.md               # 定岗映射评测约定
│   ├── seen_jobs.json               # 运行时：id 去重
│   └── unexported_details.json      # 运行时：已爬详情未进 CSV
├── scripts/
│   ├── chrome_cdp.py
│   ├── scrape_list.py
│   ├── scrape_details.py
│   ├── clean_classify_input.py
│   ├── clean_details.py
│   ├── export_skillver_csv.py
│   ├── eval_position_mapping.py     # 定岗映射评测
│   ├── boss_common.py               # 共享运行时（非 CLI）
│   ├── job_schema.py
│   └── ensure_uv_env.py
└── tests/
```

工作数据落在 `data/<搜索词>/` 与全局 `seen_jobs.json` / `unexported_details.json`，不进 skill 包。

---

## 常见问题

**爬一半停了，之前抓到的会丢吗？** 不会。列表每页写、详情每条写、seen 按 id 更新；未导出详情下次导出还会并入。从 `next_list_start_page` 续即可。

**用户描述和 58 岗对不上怎么办？** 先按用户原话当 `--query` 去搜。归类阶段由 Agent 映射到 catalog 原名或标 `null`；不要发明岗名，也不要用规则表顶替失败的 JSON。

**为什么用 CDP 而不是 Selenium / Playwright？** 受控自动化浏览器体积大、指纹明显，更容易触发风控。本工具连接你已登录的真实浏览器，复用真实会话与指纹，调用页面内搜索接口拿明文薪资，更稳也更克制。

**支持哪些浏览器？** 当前只支持 Windows。`--setup-chrome` 先找 Edge，没有再用 Chrome。Firefox / Safari 不支持。不用时：`python3 scripts/chrome_cdp.py --stop-chrome`（只关隔离 profile）。

---

## 许可

MIT。使用前请阅读本文顶部的**免责声明**。
