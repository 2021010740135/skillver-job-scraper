# Changelog

本仓库以 **Skillver 职位采集**（`skillver-job-scraper`）为产品名。

## 2.6.0

### 新增

- **分流评测集**：`data/eval/skillver_position_route_v1.json` + `scripts/eval_position_route.py`
  - 主指标：误放率 FPR、Precision@accept（见 `data/eval/README.md`）
  - 初版 43 条为 draft 金标，须人工改为 `human`
- **按企业采集（YATN）**：`data/yatn/companies.csv` + `scripts/scrape_company_jobs.py`
  - 多关键词（全称/品牌/别名）BOSS 召回；不按岗位 base 城过滤；丢掉日薪
  - Agent 契约 `references/company-job-match.md`：列表先分流（无 JD）→ `score > 70` 再开详情 → 导出
  - 宁缺毋滥；意图族两段式；Agent 向测试开发可归 `Agent工程师`
  - 默认 S+A 全量；入口 `boss-company-jobs`
- 单测 `tests/test_company_jobs.py`（mock，不连 Chrome）

### 文档

- `SKILL.md` / `README.md` / `AGENTS.md` 补充企业路径说明

## 2.5.1 — 初始对外版本

### 功能

- 标准岗分步 CLI：`--drain-inventory` / `--list-only` / `--details-from-decisions`
- Agent 内置模型按 `references/classify-decisions.md` 归类（无脚本内 DeepSeek）
- 导出 Skillver `job_YYYYMMDD.csv`；USCC 人审后原地回填
- 详情 `location` 提取与 `--city` 回退；`write_match_skip_report` 可用

### 文档

- 中文单语 `README.md` + `SKILL.md`；短版 `AGENTS.md`
- 面向任意 Agent（含 WorkBuddy）与 CLI；含免责声明
