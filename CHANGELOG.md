# Changelog

本仓库以 **Skillver 职位采集**（`skillver-job-scraper`）为产品名。

对外版本从 **1.0.0** 起算。下面 2.x 为定版前的实验记录。

## 1.0.0（最初版本）

### 标准岗主路径定型

- 拆开的 CLI：浏览器 / 列表 / 清洗 A / 详情 / 清洗 B / 导出
- `--query` 自由搜索；归类对上 58 岗任一即开详情
- 默认每批在同一列表 CDP 会话连续抓 4 页后归类；每批只做一次登录探测，页间随机等待 12–22 秒
- 不设总翻页上限；`--min-details` 只作停翻目标；已映射帖全部开详情
- `seen` 只按 `encrypt_job_id`；未导出详情记在 `unexported_details.json`
- Windows 优先 Edge
- 定岗映射评测约定 + `scripts/eval_position_mapping.py`
- README 按协作版式重写（特性 / 循环 / 版本迭代 / TODO / FAQ）

## 2.18.0

### 按页映射、详情全开、未导出记账

- 每抓 1 页列表就归类；累计映射数不够且还能翻页就继续，不设翻页上限
- `--min-details` 只作停翻目标（最多 50）；最后一页多出来的已映射帖全部开详情
- 站点映射不够时如实结束，不凑数
- 详情成功写入 `data/unexported_details.json`；CSV 写成功后去掉，避免风控换来的详情浪费

## 2.17.0

### 去掉 pending 队列与 drain

- 删除 `pending_details` / `pending_export`、`--drain-inventory`，以及按岗计数 / 队列入队等死代码
- `seen` 只按 `encrypt_job_id` 去重；详情只开本批决策里对上的岗
- 导出读本次 `details.json`，已 exported 的 id 跳过

## 2.16.1

### 导出不再按「一企一标准岗」丢行

- 同一标准岗下可有多条 BOSS 帖；CSV 全部保留
- 去重只认 `encrypt_job_id`

## 2.16.0

### 自由搜索词 + 58 岗全映射 + 全局 seen

- `--query` 进搜索框，不必是 catalog 原名；`--position-name` 仅作别名
- 归类对上 58 个标准岗任一即开详情，不再「本轮只入库一个岗」
- 导出按每行自己的标准岗填 intent
- 全局 `data/seen_jobs.json`（`encrypt_job_id`）在列表 / 归类 / 详情 / 导出去重；`null` 也落盘

## 2.15.0

### Windows 优先 Edge + Agent 安装文档

- Windows 启停 CDP：先 Edge，没有再用 Chrome；不加浏览器开关
- `--copy-login-state` 与 `--stop-chrome` 按同一顺序认 Edge / Chrome
- 新增 `references/install.md`：Agent 只读文档即可把 skill 拷到本机，不另写安装脚本

## 2.14.0

### 拆 CLI + 两段清洗 + 瘦字段

- 删除单体 `boss_cdp_raw.py` 以及 `--analysis` / `--keyword` 批跑 / 旧 list·detail CSV
- 拆成独立 CLI：Chrome、列表、详情、清洗 A、清洗 B、导出
- 清洗 A：`list_batch` → `classify_input`（只留归类字段；去掉 `security_id` / `lid` / `job_link`）
- 清洗 B：详情只留导出字段
- 清洗只丢多余键，不因实习 / 日薪丢卡片
- `jobs.json` 仍保留 URL 字段，供详情 CLI 打开页面
- `SKILL.md` 收成导航；细节拆成 7 份 `references/`

## 2.13.0

### 去掉按企业旁路

- 删除 `scrape_company_jobs.py`、`companies.csv`、企业 CSV 导出、`score>70` 契约
- 删除配套评测：`eval/`、`eval_position_route.py`
- 只保留标准岗：`boss_cdp_raw.py` → Agent 归类 → `export_skillver_csv.py`

## 2.12.0

### 去掉 USCC

- 标准岗 CSV 不再含「统一社会信用代码」，不再做工商检索 / cache / 人审回填
- 人机闸门只剩登录与最终 CSV 核验

## 2.11.0

### 目录重整

- 公共资产平铺在 `data/`：`city_codes.json`、`companies.csv`、`position_catalog.json`
- 评测独立为仓库根 `eval/`
- 爬取产物按搜索词建目录：`data/<搜索词>/jobs.json`（以及 details / seen / 归类文件）
- 删除 `data/skillver/`、`data/yatn/` 及品牌页 querylist 死代码
- 依赖只认 **uv**（`pyproject.toml` + `uv.lock`），去掉 `requirements.txt`

## 2.10.0

### 企业列表改走搜索（停用品牌页）

- **`--scrape-brand-jobs` 停用**（`querylist.json` 易 5 页 `code=37`）。企业列表只走 `scrape_list` / `search/joblist.json`
- 每家一次搜索：`brand_name` + 表中 `city`（可用 `--city 全国` 覆盖）+ **求职类型全职**（`jobType=1901`）
- 列表后本地过滤：`encrypt_brand_id`（无 brand_id 则品牌名匹配）、日薪、实习；不拆经验档
- 默认 8 页；多家之间间隔 45–90s；`code != 0` 立刻停
- `boss_cdp_raw.py` 新增 `--job-type`；搜索 XHR 读取 API `code`

## 2.9.1

### 品牌页页级断点

- 每成功一页写入 `in_progress.last_ok_page`；中断后从 **下一页** 续爬，不再把未完成组合从第 1 页重打
- 旧 v2 断点（只有 `completed`）仍可用；缺页码时按该组合已写入 JSON 的条数推算（15 条/页，例如 75 条 → 第 6 页）
- 开始抓取时只要 `jobs_output` 存在就加载，避免无断点时覆盖已有列表
- `code=37` 等接口异常仍立即停止，不重试

## 2.9.0

### 环境自举（uv + 项目 .venv）

- `--check` 顺序：**有没有 uv → 没有则安装 → `uv sync` → CDP → 登录**
- 依赖装进本 skill 的 `.venv`，不污染用户系统 Python
- `uv sync` 失败时自动改走清华 / 阿里云镜像；也可设 `UV_INDEX_URL`
- 抓取入口（`boss_cdp_raw.py` / `--scrape-brand-jobs` 等）在缺项目环境时会切到 `.venv` 再跑

## 2.8.0

### 品牌页列表（替换 2.7.x 自动拆分）

- **只爬技术 + 产品**（`--position`，默认 `技术,产品`），再按 **工作经验**（`--experience`）筛选
- 经验支持用户说法映射：`不限` / `实习` / `不要实习` / 下拉标签 / 代码（逗号分隔）
- **去掉自动拆分探测**（不再按城市/薪资/学历递归拆桶凑全量）
- 每组只翻网站能翻到的页（最多 14 页）；数量多少都接受
- **列表阶段不过滤**日薪 / 猎头 / 匿名（无标题或岗位 ID 的坏卡片仍丢）
- 节奏对齐 `boss_cdp_raw.scrape_list`：首屏导航后滚动，翻页间隔 12–22s；接口异常即停
- 断点改为「类型×经验」组合级（v2）；每页写入 `jobs_output`
- `companies.csv` 阶跃星辰补上 `brand_id`

## 2.7.1

### 稳定性加固（品牌页全量模式）

- **拟人化动作**：`human_scroll` / `human_mouse_jitter` 从 `scrape_list` 闭包提升为 `boss_cdp_raw` 模块级函数；品牌页模式在宿主页导航后与每次 API 请求前复用同一套动作，与搜索路径行为一致
- **断点续爬**：`BrandCheckpoint`（`<jobs_output>.checkpoint.json`）
  - 叶桶完成、拆分决策（含兜底 base_jobs）即时落盘；中断后重跑零请求跳过已完成桶
  - 每完成一家企业即合并写一次 jobs_output（与搜索路径「每页写入」同思路）
  - 全部完成才删除断点文件（下次全量刷新）；中断则保留供续爬
- 触顶判定不再依赖 `hasMore`：收满 200 条即视为触顶拆分（cap 边界页 hasMore 语义不可靠）

## 2.7.0

### 新增

- **品牌页全量列表**：`scrape_company_jobs.py --scrape-brand-jobs`
  - 走 `/wapi/zpgeek/brand/job/querylist.json`，按 `brand_id` 列品牌在招全部岗位（解决关键词搜索 10 页上限 + 城市过滤 + 相关性导致的覆盖不全）
  - 单筛选桶上限 200 条；超桶自动按 职位类型 → 城市 → 薪资 → 学历 → 经验 递归拆分（positionList/cityList 用 API 返回的桶计数预判）
  - 学历/经验拆分会先翻满父桶 200 条兜底，避免漏「学历不限/经验不限」岗位
  - `companies.csv` 新增可选 `brand_id` 列（BOSS 品牌页 URL 末段，`|` 分隔多品牌；MiniMax 已配）
  - 请求节流（15–25s 随机）+ 限流退避（60/180/300s）+ 单次 150 请求预算；限流即停，不硬闯
  - 沿用既有规则：丢日薪、过滤猎头/匿名、按 encrypt_job_id 去重，输出与 `--scrape-list` 同构，下游打分/详情/导出不变

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
