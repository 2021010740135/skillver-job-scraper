# AGENTS.md

指引给未来的 Coding agent。先读这份，再动代码。

## 这是什么

`Skillver 职位采集`（仓库目录可仍叫 `boss-zhipin-scraper`）——通过 Chrome CDP 连接**用户本人已登录的 Chrome**，按 Skillver 标准岗分步采集公开职位（列表 + 详情），导出 `job_YYYYMMDD.csv`，并用 **Agent 网络检索 + 人工确认** 补全 USCC / 工商全称。当前内置 BOSS直聘适配；仅用于个人求职分析，非大规模爬虫（见 `CONTRIBUTING.md` 的合规一节与 README 免责声明）。

面向 Skillver 时，**主路径目录是 `data/skillver/`**（标准岗 catalog + jobs/details/exports/seen + USCC 缓存）。

**最小 Skill 范围**（见 `SKILL.md`）：分步抓取 + **Agent 内置模型归类** + 导出 + USCC 检索闸门。不要把摘要/分析/企查查/脚本内 DeepSeek 加回主路径。文档以中文 `README.md` + `SKILL.md` 为准，**不再维护双语 README**。

## 目录结构

```
scripts/boss_cdp_raw.py        # 核心：CDP 抓取 CLI（drain / list-only / details-from-decisions）
scripts/export_skillver_csv.py # 详情 → Skillver CSV（job_YYYYMMDD）+ seen v2 + USCC cache 应用
references/classify-decisions.md # Agent 归类决策 JSON 契约（必打包）
data/city_codes.json           # 全量城市码表（300+ 城市，外置）
data/skillver/                 # 主路径：position_catalog.json 可提交；其余本地忽略
tests/test_chrome_setup.py     # unittest，全 mock，不依赖真实 Chrome/网络
tests/test_export_skillver_csv.py
tests/test_skillver_p6.py      # Skillver 分步 + Agent 决策 mock 测试
pyproject.toml                 # 入口 boss-scraper / boss-export-skillver
requirements.txt               # 仅 requests + websocket-client
SKILL.md / README.md / CHANGELOG.md / CONTRIBUTING.md
```

**重要边界：核心抓取逻辑都放 `scripts/boss_cdp_raw.py`，不要随手把爬虫拆文件**（见 `CONTRIBUTING.md`「单文件原则」）。`docs/` 与 `data/reports/` 被 `.gitignore` 忽略，是本地产物，不要提交。**例外**：`data/city_codes.json`、`data/skillver/position_catalog.json`、`references/` 是数据/契约资产；`export_skillver_csv` 是抓取后的独立工具，不要把导出/USCC 写盘逻辑塞回爬虫单文件。

### Skillver 流水线（先读 SKILL.md / README 对应节）

- 抓取必须 `--position-name`；分步：`--drain-inventory` → 循环 `--list-only` → Agent 写决策 → `--details-from-decisions`。
- 脚本规则只过滤猎头/匿名；标准岗归类**全部**由 Agent 按 `references/classify-decisions.md` 完成（无脚本内 LLM）。
- 他岗挂 `pending_details` 库存；`--min-details` 默认 5、上限 50（本轮目标新增，Agent 循环控制）。
- 单表 `data/skillver/seen_jobs.json`（version 2）。
- 导出独立脚本按 `pending_export`；默认 `job_YYYYMMDD.csv`；USCC 确认后**原地改 CSV**。
- USCC：Agent 网络检索 + 人工确认写 cache（**禁止**企查查 CDP 批量爬）。

## 环境与命令

- Python **>=3.10**，依赖只有 `requests` + `websocket-client`。用项目里的 `.venv`。
- 包管理用 `uv`（仓库有 `uv.lock`），也可 `pip install -r requirements.txt`。
- 跑测试：`python3 -m unittest tests.test_chrome_setup tests.test_export_skillver_csv tests.test_skillver_p6`。
- **不需要** `.env` / DeepSeek（归类用 Agent 内置模型）。
- 语法自检：`python3 -m py_compile scripts/boss_cdp_raw.py scripts/export_skillver_csv.py`。
- 实跑抓取：`python3 scripts/boss_cdp_raw.py --setup-chrome`，登录后按 `SKILL.md` 分步调用。

## 改代码时的硬规则

1. **版本号四处一致**：`scripts/boss_cdp_raw.py` 的 `__version__`、`pyproject.toml`、`SKILL.md`、`README.md` 必须同步。
2. **异常处理**：禁止 bare `except:`，必须捕获具体类型。
3. **改了用户可见行为 → 更新 `README.md`；有意义变更 → `CHANGELOG.md` 顶部加一条。**
4. **文档中文单语**：只维护 `README.md`（不要再加 `README.en.md`）。
5. **本地开发不要求创建 commit**；用户明确要求时才用 Conventional Commits。

## 架构关键点（容易踩坑）

- `scripts/boss_cdp_raw.py` 是长单文件：CDPSession、列表 wapi、详情新 tab、main。
- 列表页 vs 详情页路径完全不同。
- CDP target 统一通过 `create_page_session`；`wait_for_login` 才 `background=False`。
- 同一 Chrome 默认 context 下新 target 共享 cookies。

## 本地开发流程

本项目默认只在当前工作区进行本地开发。开始前先检查 `git status` 和相关 diff，识别并保留用户已有修改；不要为了开始任务而要求工作树干净，也不要覆盖、回滚或丢弃不属于当前任务的改动。

本地开发不以 GitHub Issue、Fork、分支、commit、Push 或 Pull Request 为前置条件。完成代码、mock 测试、README/SKILL 和 CHANGELOG 后，直接报告本地修改与验证结果。允许使用 `git status`、`git diff` 等只读命令保护现有工作；只有用户在当前任务中明确要求时，才执行会改变 Git/GitHub 状态的操作。
