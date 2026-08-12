# Changelog

本仓库以 **Skillver 职位采集**（`skillver-job-scraper`）为产品起点。更早的提交历史仅作技术沿革，不再逐条维护。

## 2.5.1 — 初始对外版本

### 功能

- 标准岗分步 CLI：`--drain-inventory` / `--list-only` / `--details-from-decisions`
- Agent 内置模型按 `references/classify-decisions.md` 归类（无脚本内 DeepSeek）
- 导出 Skillver `job_YYYYMMDD.csv`；USCC 人审后原地回填
- 详情 `location` 提取与 `--city` 回退；`write_match_skip_report` 可用

### 文档

- 中文单语 `README.md` + `SKILL.md`；短版 `AGENTS.md`
- 面向任意 Agent（含 WorkBuddy）与 CLI；含免责声明
