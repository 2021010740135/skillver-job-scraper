# AGENTS.md

给 Coding Agent 的短说明。先读这份，再动代码。

## 项目

**Skillver 职位采集**（仓库：`skillver-job-scraper`）——本机已登录 Chrome（CDP）采集公开职位：

1. **标准岗路径**：分步搜岗 → Agent 归类 → Skillver CSV
2. **按企业路径（YATN）**：企业表召回列表 → Agent `score`+标准岗（>70，宁缺毋滥）→ 仅录取开详情 → 后端 CSV  

分流评测集：`data/eval/`（主指标：误放率 FPR、Precision@accept）。见 `data/eval/README.md`。

当前数据源：BOSS直聘。仅个人求职分析，见 `README.md` 免责声明。

执行手册：`SKILL.md`。契约：`references/classify-decisions.md`、`references/company-job-match.md`。

**最小范围**：上述两条采集 + Agent 归类/打分 + 导出。不要把摘要分析、企查查、脚本内 DeepSeek、智联/北森补爬加回主路径。文档只维护中文 `README.md` + `SKILL.md`。

## 关键路径

```
scripts/boss_cdp_raw.py            # 标准岗 CDP CLI
scripts/export_skillver_csv.py     # 标准岗 → job_YYYYMMDD.csv
scripts/scrape_company_jobs.py     # 按企业采集 / 打分应用 / 导出
references/classify-decisions.md
references/company-job-match.md
data/city_codes.json
data/skillver/position_catalog.json
data/yatn/companies.csv            # 可提交；jobs/details/exports 本地忽略
data/eval/                         # 标准岗分流金标评测集（可提交）
scripts/eval_position_route.py     # FPR + Precision@accept
tests/test_*.py
```

标准岗抓取逻辑保持在 `boss_cdp_raw.py` 单文件；企业路径用独立脚本，可 import 复用 CDP 助手，不要把企业循环焊进标准岗 `main`。导出写盘不要塞回爬虫单文件。

## 命令

- Python >=3.10；`requests` + `websocket-client`
- 测试：`python -m unittest tests.test_chrome_setup tests.test_export_skillver_csv tests.test_skillver_p6 tests.test_company_jobs tests.test_eval_position_route`
- 分流评测：`python scripts/eval_position_route.py --pred <match_scores.json>`
- 语法：`python -m py_compile scripts/boss_cdp_raw.py scripts/export_skillver_csv.py scripts/scrape_company_jobs.py`
- 实跑：`--setup-chrome` 后按 `SKILL.md`（标准岗或按企业）

## 硬规则

1. 版本号四处一致：`boss_cdp_raw.py` `__version__`、`pyproject.toml`、`SKILL.md`、`README.md`（企业脚本 `__version__` 保持同版本）
2. 禁止 bare `except:`
3. 用户可见行为变 → 更新 `README.md`；有意义变更 → `CHANGELOG.md` 顶部加一条
4. 本地开发默认不 commit/push，除非用户明确要求
5. 开始任务前用 `git status`/`git diff` 识别并保留用户已有修改
