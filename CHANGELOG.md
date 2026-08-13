# Changelog

本仓库以 **Skillver 职位采集**（`skillver-job-scraper`）为产品名。

## 2.10.0

### 新增

- **定岗映射评测集**：`data/eval/skillver_position_mapping_v1.json`（70 条）
  - 测「用户叫法/自然语言 → 58 标准岗」映射准确率，与分流评测（`route_v1`）互补
  - 58 岗全覆盖（`alias` 代表叫法）+ 5 `semantic`（规则零命中、语义兜底负责）+ 5 `reject`（应拒）+ 2 `ambiguous`（歧义走人工确认，自动评测跳过）
  - 初始全 `draft`，须人工改为 `human` 后作为正式金标
- **评测脚本**：`scripts/eval_position_mapping.py`（两个指标：岗名准确率 `position_accuracy`、误收率 `false_accept_rate`）
- **规则层基线实测**：58 alias 样例全对（58/58）；应拒 5/5 全拒（误收 0）；语义样例规则层一律不自动定（正确行为，交语义兜底）→ 整体岗名准确率 **94.1%**（64/68）、误收率 **0%**
- **规则匹配改进（最长别名优先）**：多候选时若某命中别名是另一命中别名的严格超串则淘汰较短者（如「具身智能研究」⊃「具身智能」）——修复嵌套歧义（`具身智能研究岗位` 现可自动定岗），SKILL.md Step 1 同步规则
- **评测集扩充真实用户叫法**：70 → 109 条（alias 84 / semantic 12 / reject 9 / ambiguous 4），新增 26 条口语化叫法（智能体工作流、搜推广、RLHF 对齐、SLAM 建图等）与 7 条语义兜底、4 条应拒、2 条歧义
  - 扩充后规则层基线：89.5%（94/105）、误收 0%；26 条真实叫法全对，11 条 mismatch 全为 semantic（规则零命中、交语义兜底，符合设计）

### 文档

- `data/eval/README.md`：新增映射评测集章节（字段 / 指标 / 跑法 / 扩充方法）
- 版本号四处同步 2.10.0

## 2.9.0

### 新增

- **断点续爬（task_state）**：每个标准岗一个 `data/skillver/task_state_<岗名>.json`
  - drain / list-only / details-from-decisions 每次结束时**脚本自动写**状态（阶段、批次、下一批页码、本轮新增详情数、min-details、城市）
  - 任何标准岗命令启动时**自动检测**上次状态并打印续爬提示（按是否达标给出建议）
  - 与既有落盘机制闭环：列表每页写、详情每条写、seen 每条更新——中断不丢数据，续爬重跑同命令即按 seen 跳过已抓
  - `print_resume_hint` 按 `new_details_count ≥ min_details` 区分建议（达标 → export；未达标 → 继续列表）

### 文档

- `SKILL.md`：断点续爬小节 + 默认路径表；`README.md`：特性 + 目录 + TODO 第 3 条标记完成；`.gitignore` 忽略 `task_state_*.json`
- `README.md` 全面重写：按「简介 → 快速开始 → 两种路径 → 标准岗循环 → 断点续爬 → 定岗 → YATN → 导出 → 安装 → 约定 → 结构 → FAQ → 路线图」重组，消除章节重复与编号冲突
- 版本号四处同步 2.9.0

## 2.8.1

### 修复

- **「所在城市」与「岗位base地」同值**：详情页 location 多不带 `·` 分隔（如 `上海青浦区华为练秋湖研发中心`），`city_from_location` 原按 `·` 取第一段导致返回整串、两列退化相同
  - `city_from_location` 改为：优先 `·` 分隔取首段；无 `·` 时用 `data/city_codes.json` 城市名做**最长前缀匹配**（如 `上海青浦区…` → `上海`）；仍无则回退 `--city`
  - 修正补充：前缀匹配**优先于** `·` 分割（地址中段藏 `·` 时，如 `上海浦东新区…T5(模力·栈)T5`，`·` 分割会取错段；城市名总在地址开头，前缀匹配对两种格式都正确）
  - `detail_to_row`：`岗位base地` 保留完整办公地址（location 原值），`所在城市` 为提取出的城市名——两列各司其职
  - 测试同步：`test_valid_detail_columns` / `test_location_without_city_cli_fallback_exports` 断言更新
- **定岗规则表补齐 58/58**：`position_aliases.json` 补 14 个机器人细分岗别名（伺服驱动/机械臂结构/触觉力觉/验证测试等），别名总数 44→58 岗、128→170 条，跨岗别名零重复

### 文档

- 版本号四处同步 2.8.1

## 2.8.0

### 变更

- **移除 USCC / 工商补全功能**（标准岗路径）
  - `export_skillver_csv.py`：删除 `--uscc-cache` 参数与全部 USCC 逻辑（cache 加载/应用、`legal_name` 重写、USCC 校验、去重 key 的 uscc 优先分支）
  - CSV 列精简：移除「企业名称」「统一社会信用代码」两列，保留「招聘品牌名」等 8 列
  - 人机闸门由三处减为两处：`WAIT_LOGIN` / `WAIT_CSV_REVIEW`（删除 `WAIT_USCC_REVIEW`）
  - 文档同步：`SKILL.md`（Step 6 USCC 整节删除、能力/原则/矩阵/提示词清理）、`README.md`、`start.md`、`AGENTS.md`、`references/classify-decisions.md`、`pyproject.toml` description

### 文档

- 版本号四处同步 2.8.0（`boss_cdp_raw.py` / `scrape_company_jobs.py` / `pyproject.toml` / `SKILL.md` / `README.md`）

## 2.7.0

### 新增

- **定岗规则表**：`data/skillver/position_aliases.json`（用户叫法/关键词 → 58 标准岗原名）
  - 定岗匹配改为**先规则后语义**：规则唯一命中直接定岗；歧义（多候选）列出候选请用户手动确认，确认后回写规则表；零命中才由 Agent 内置模型语义映射
  - 规则层由 **Agent 编排执行**（Step 1 定岗阶段），脚本 `resolve_position` 严格原名校验保持不变，脚本零改动
  - 回写规则表：`「该叫法 → 所选岗」` 追加去重，同输入下次直接命中

### 文档

- `SKILL.md`：version 2.7.0；执行原则 / Step 1 定岗流程 / 资源表 / 安装清单补充规则表
- `README.md`：version 2.7.0；特性与核心约定补充定岗规则；TODO 第 2 条标记完成
- 修正 `scripts/boss_cdp_raw.py` `__version__` 由 2.5.1 → 2.7.0（此前与其余三处不一致）

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
