# AGENTS.md

给 Coding Agent 的短说明。先读这份，再动代码。

## 项目

**Skillver 职位采集**（仓库：`skillver-job-scraper`）——通过本机已登录 Chrome（CDP）按 Skillver 标准岗分步采集公开职位，Agent 内置模型归类，导出 `job_YYYYMMDD.csv`，USCC 靠网络检索 + 人审回填。当前内置 BOSS直聘适配。仅个人求职分析，见 `README.md` 免责声明。

主数据目录：`data/skillver/`。执行手册：`SKILL.md`。归类契约：`references/classify-decisions.md`。

**最小范围**：分步抓取 + Agent 归类 + 导出 + USCC 闸门。不要把摘要分析、企查查、脚本内 DeepSeek 加回主路径。文档只维护中文 `README.md` + `SKILL.md`。

## 关键路径

```
scripts/boss_cdp_raw.py          # CDP CLI：drain / list-only / details-from-decisions
scripts/export_skillver_csv.py   # 详情 → job_YYYYMMDD.csv + seen + USCC cache
references/classify-decisions.md
data/city_codes.json
data/skillver/position_catalog.json
tests/test_*.py
```

抓取逻辑保持在 `boss_cdp_raw.py` 单文件；导出/USCC 写盘不要塞回该文件。`data/skillver/` 下 jobs/details/exports/seen/cache 为本地产物（gitignore），勿提交。

## 命令

- Python >=3.10；依赖仅 `requests` + `websocket-client`（`requirements.txt` / `.venv`）
- 测试：`python -m unittest tests.test_chrome_setup tests.test_export_skillver_csv tests.test_skillver_p6`
- 语法：`python -m py_compile scripts/boss_cdp_raw.py scripts/export_skillver_csv.py`
- 实跑：`--setup-chrome` 登录后按 `SKILL.md` 分步调用

## 硬规则

1. 版本号四处一致：`boss_cdp_raw.py` `__version__`、`pyproject.toml`、`SKILL.md`、`README.md`
2. 禁止 bare `except:`
3. 用户可见行为变 → 更新 `README.md`；有意义变更 → `CHANGELOG.md` 顶部加一条
4. 本地开发默认不 commit/push，除非用户明确要求
5. 开始任务前用 `git status`/`git diff` 识别并保留用户已有修改，勿覆盖无关改动
