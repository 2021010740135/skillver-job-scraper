# AGENTS.md

给 Coding Agent 的短说明。先读这份，再动代码。

## 项目

**Skillver 职位采集**（仓库：`skillver-job-scraper`）——本机已登录浏览器（Windows 优先 Edge；CDP）按任意搜索词采集，映射到 **58 个 Skillver 标准岗**：搜索 → Agent 归类 → Skillver CSV。

当前数据源：BOSS直聘。仅个人求职分析，见 `README.md` 免责声明。

执行手册：`SKILL.md`（导航）。细节只放 `references/` 一级文档。归类契约：`references/classify-decisions.md`。

**最小范围**：标准岗采集 + Agent 归类 + 导出。不要把按企业旁路、摘要分析、企查查、脚本内 DeepSeek、智联/北森补爬加回主路径。文档只维护中文 `README.md` + `SKILL.md`。

## 关键路径

```
scripts/chrome_cdp.py              # 环境 / 登录
scripts/scrape_list.py             # 列表 → jobs.json + list_batch
scripts/clean_classify_input.py    # 清洗 A → classify_input
scripts/scrape_details.py          # 按决策开详情
scripts/clean_details.py           # 清洗 B
scripts/export_skillver_csv.py     # Skillver CSV
scripts/boss_common.py             # 共享运行时（无 main）
scripts/job_schema.py              # 字段白名单
references/*.md                    # 八份一级说明（含 install.md）
data/city_codes.json
data/position_catalog.json
tests/test_*.py
```

一个脚本一件事。不要把 CLI 重新合成 `boss_cdp_raw.py`。导出写盘不要塞回爬虫。

## 命令

- Python >=3.10；依赖由 **uv + 项目 `.venv`** 管理（`--check` 自举，勿 pip 进系统 Python）
- 测试：`python -m unittest tests.test_chrome_setup tests.test_export_skillver_csv tests.test_skillver_p6 tests.test_ensure_uv_env tests.test_clean_jobs`
- 语法：`python -m py_compile scripts/boss_common.py scripts/chrome_cdp.py scripts/scrape_list.py scripts/scrape_details.py scripts/clean_classify_input.py scripts/clean_details.py scripts/export_skillver_csv.py scripts/job_schema.py`
- 实跑：`scripts/chrome_cdp.py --setup-chrome` 后按 `SKILL.md`

## 硬规则

1. 版本号四处一致：`boss_common.py` `__version__`、`pyproject.toml`、`SKILL.md`、`README.md`
2. 禁止 bare `except:`
3. 用户可见行为变 → 更新 `README.md`；有意义变更 → `CHANGELOG.md` 顶部加一条
4. 本地开发默认不 commit/push，除非用户明确要求
5. 开始任务前用 `git status`/`git diff` 识别并保留用户已有修改
