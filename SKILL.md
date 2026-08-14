---

name: skillver-job-scraper
description: >
  通过本机已登录浏览器（Windows 优先 Edge，其次 Chrome；CDP）按 Skillver 标准岗分步采集公开职位，由 Agent 内置模型归类，
  导出 Skillver job_YYYYMMDD.csv。
  用户提到 Skillver、标准岗、--query、--position-name、职位采集、
  BOSS直聘、zhipin，或要从详情导出招聘 CSV 时，应优先使用本 skill；即使未点名
  skill 名，只要任务属于该流水线也应触发。本 skill 必须人机协同：登录数据源、
  核验最终 CSV。
  禁止在脚本内再调 DeepSeek 或其它 API 做归类。
version: 2.18.0
author: skillver-job-scraper
license: MIT
platforms: [windows]
metadata:
  hermes:
tags: [scraper, jobs, career, cdp, chrome, skillver, zhipin]

---

# Skillver 职位采集（skillver-job-scraper）

当前采集适配 BOSS直聘。编排按 Skillver 标准岗。不要另写爬虫，不要在脚本内调 DeepSeek。

## When to use

用户要从已登录浏览器按任意搜索词采公开职位，映射到 `position_catalog.json` 的 58 个标准岗，并导出 `job_YYYYMMDD.csv`。

## Do NOT use

- 脚本内 LLM / DeepSeek / `.env` 打分
- 按企业名单旁路、企查查、摘要分析、智联/北森补爬
- 把日薪（`元/天`）硬改成社招 `NK-MK`（导出侧跳过即可）
- 发明 catalog 里没有的岗名



## What（脚本与 references，一级）

环境用 **uv + 项目** `.venv`。任意 `python` 跑 `--check` 即可自举。


| 步骤   | 脚本                                | 说明                                                                         |
| ---- | --------------------------------- | -------------------------------------------------------------------------- |
| 部署   | Agent 按文档拷文件                      | `[references/install.md](references/install.md)`                           |
| 环境登录 | `scripts/chrome_cdp.py`           | `[references/chrome-setup.md](references/chrome-setup.md)`                 |
| 列表   | `scripts/scrape_list.py`          | `[references/scrape-list.md](references/scrape-list.md)`                   |
| 清洗 A | `scripts/clean_classify_input.py` | `[references/clean-classify-input.md](references/clean-classify-input.md)` |
| 归类   | Agent 内置模型                        | `[references/classify-decisions.md](references/classify-decisions.md)`     |
| 详情   | `scripts/scrape_details.py`       | `[references/scrape-details.md](references/scrape-details.md)`             |
| 清洗 B | `scripts/clean_details.py`        | `[references/clean-details.md](references/clean-details.md)`               |
| 导出   | `scripts/export_skillver_csv.py`  | `[references/export-csv.md](references/export-csv.md)`                     |


数据：`data/city_codes.json`、`data/position_catalog.json`（58 岗）。产物在 `data/<搜索词>/`。去重用全局 `data/seen_jobs.json`（主键 `encrypt_job_id`）。未进 CSV 的详情记在 `data/unexported_details.json`。

**人机闸门只有两处**：`WAIT_LOGIN`、`WAIT_CSV_REVIEW`。归类成功后不要加人闸门，直接开详情。

## How

本机还没有本 skill 时，先按 `[install.md](references/install.md)` 部署。已在本机则从第 1 步开始。

1. 锁定 `--query`（搜索框，任意词）、城市（默认上海）、可选筛选、`--min-details`（用户目标，默认 5，上限 50）。这是**停翻页的最低映射数**，不是详情截断。只要导出则可跳到第 8 步。`--position-name` 只是 `--query` 的别名。
2. 按 `[chrome-setup.md](references/chrome-setup.md)` `--check`；不通则 `--setup-chrome`，进入 `WAIT_LOGIN`。
3. 对页 `P=1,2,…`（**不设翻页上限**）：按 `[scrape-list.md](references/scrape-list.md)` 只抓 **1 页** → `jobs.json` + `list_batch_P.json`。已在全局 seen 的 `encrypt_job_id` 不再进本页。
4. 按 `[clean-classify-input.md](references/clean-classify-input.md)` 写出 `classify_input_P.json`。
5. 按 `[classify-decisions.md](references/classify-decisions.md)` 写 `classify_decisions_P.json`。强制自检：纯 JSON、`schema_version===1`、`results.id` 与输入 `jobs.id` 集合相等、每个 `position_name` 为 58 岗原名或 `null`。失败最多 3 次 → 打断点，**不开详情、不用规则顶替**。
6. 累计各批 `position_name != null` 的条数。**还不够且 `next_list_start_page` 有值** → `P+=1` 回到第 3 步（**此阶段不要开详情**）。够了、或没有下一页（站点不够可以少于目标）→ 第 7 步。
7. 按 `[scrape-details.md](references/scrape-details.md)` 一次传入**全部** `classify_decisions_*.json`。**已映射帖全部开详情**（最后一页多出来的也全开，不砍到 `--min-details`）。`null` 写入 seen 后跳过。
8. 按 `[clean-details.md](references/clean-details.md)` 再 `[export-csv.md](references/export-csv.md)`：先 `--dry-run` 再正式导出。导出成功的 id 从 `data/unexported_details.json` 去掉；中途挂了下次导出会把未导出详情补进 CSV。
9. 给出 CSV 绝对路径，进入 `WAIT_CSV_REVIEW`，等「CSV 已核验」再结束。

清洗 **只丢多余字段**，不因实习/日薪丢岗位。`security_id` / `lid` 留在 `jobs.json`，不进 classify_input。