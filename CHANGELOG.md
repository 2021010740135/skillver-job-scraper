# Changelog

## 未发布

### 变更
- **2.5.0 Agent 归类主路径**：标准岗改为分步 CLI（`--drain-inventory` / `--list-only` / `--details-from-decisions`）；标准岗归类改由 Agent 内置模型按 `references/classify-decisions.md` 写决策 JSON；删除脚本内 DeepSeek / `.env` 归类；猎头与匿名仍用规则过滤；他岗继续挂库存；`--min-details` 默认 5、上限 50（超限压到 50）；USCC 确认后原地改 CSV；Skill 包须含 `references/` + `requirements.txt`
- **最小 Skill 2.4.0**：按 Mapping-Skill 风格重写 `SKILL.md`；删除非核心旁路脚本；入口仅保留 `boss-scraper` / `boss-export-skillver`
- USCC / 工商全称改由 Agent 公开检索 + 人工确认写入 `company_uscc_cache.json`（不再提供企查查 CDP 旁路）

### 修复
- Chrome setup 单测改为 mock `iter_chrome_process_commands`，Windows / macOS 均可识别专用 CDP profile（不再依赖 Unix `ps` 假输出）
- `--min-details` 按**本轮新增**详情计数（不再用历史累计已有数提前停抓）；日志区分「历史详情 / 本轮目标新增 / 本轮新增」

### 变更
- Skillver 导出脚本重命名为 `scripts/export_skillver_csv.py`；默认产出 `data/skillver/exports/job_YYYYMMDD.csv`；CSV 增加 `统一社会信用代码` / `招聘品牌名`，`企业名称` 在命中 USCC 缓存时回写工商全称；主体唯一键按 USCC 归并
- （历史）曾新增旁路 `enrich_company_uscc.py`（企查查）；**2.4.0 已移除**
- 移除临时脚本 `import_legacy_skillver_job0616.py` / `cleanup_skillver_job0616_csv.py` 与本地 `data/_legacy/`；文档与入口同步去掉 `job0616` 日期硬编码
- Skillver 导出适配平台 CSV 解析：JD 去掉引号并将 ASCII 逗号换成全角 `，`；按「企业/USCC + 岗位名称」去重；过滤明显 HR/销售错标与薪资低端 `<10K` 的脏数据

### 新增
- Skillver P6：跨岗库存 + 批量归类 + seen v2 索引——`seen_jobs.json` 升级为 `version:2`（`jobs` 真相表 + `by_position.pending_details/pending_export` 待办索引，无 `done`；v1 自动迁移）；标准岗主循环先完整清库存再按默认 2 页一批抓列表；批内顺序为 O(1) 去重 → 非实体规则过滤 → 高置信规则 → 批量 LLM → 保守降级 → 当前岗详情 / 他岗挂账 / none；`--min-details` 默认 20（最低详情，不硬截断）、`--page-batch-size` 默认 2、`--pages` 默认/上限 8；`--experience` / `--scale` 支持逗号与重复多选；完整决策报告 + `data/skillver/eval/review_*.csv`；（历史）离线评测脚本已在 **2.4.0 移除**
- Skillver P5：列表后智能过滤 + 详情配额——LLM 优先判「是否匹配标准岗 X」（仅 yes/no），失败则全 catalog 打分且仅 `best==X` 接受；实体公司 LLM 优先，失败降级猎头/匿名规则；默认凑满 20 详情、最多 3 页；跳过写入 `--match-report`。单测全 mock（LLM yes/no、规则降级、实体拒绝、页数/条数边界）

### 变更
- Skillver 匹配由 P5 单条 yes/no 升级为 P6 批量 JSON 归类（正式岗名仅允许 catalog 原名或 null）；`--max-details` 在标准岗路径降为 `--min-details` 兼容别名，不再截断库存/当前批详情
- Skillver 匹配 prompt：由「是否属于 X」改为全 catalog **互斥归类**（注入 58 标准岗 + few-shot + 短 CoT）；最终仍只解析 yes/no（取末行）。未加 `llm_yes` 后的规则复核闸
- Skillver P4：`boss_cdp_raw.py` 标准岗主路径——必须 `--position-name`（命中 catalog）；用岗名搜列表；默认 `data/skillver/jobs|details`；详情绑定三列岗名；成功后写 seen `has_details=true/exported=false`；已有详情跳过开页；标准岗模式忽略旧 title 过滤；`--keywords-file` 退出主路径。单测覆盖未知岗报错与 seen 跳过
- Skillver P3：导出脚本接通单表 `data/skillver/seen_jobs.json`（`encrypt_job_id` 主键）；`exported==true` 跳过，成功写出后标 `exported=true` 并持久化；`--dry-run` 不改 seen；单测覆盖连续导出防重复
- Skillver P2：独立导出脚本 `scripts/export_skillver_job0616.py`（详情 JSON → Skillver 八列 `job0616.csv`）；固定 catalog 岗名三列 + 规则解析薪资/城市；支持 `--append` / `--dry-run` / `--report`。入口 `boss-export-skillver`；测试 `tests/test_export_skillver_job0616.py`
- Skillver P1 资产：可提交 `data/skillver/position_catalog.json`（58 标准岗：`position_name` / `job_intent_id` / `job_intent_label` / `industry`）；`jobs/` / `details/` / `exports/` 目录占位（`.gitkeep`）。抓取匹配 / seen 尚未实现

### 文档
- README / README.en / AGENTS / CHANGELOG：Skillver P6（seen v2、清库存→两页一批→批量归类、min-details/8 页、筛选多选、决策报告与离线评测）；版本同步 2.3.0
- 本地开发政策：`AGENTS.md` / `CONTRIBUTING.md` 移除 GitHub Issue、Fork、分支、commit、Push、PR 前置要求；默认直接在当前工作区开发和验证，仅在用户明确要求时执行 Git/GitHub 操作
- README / README.en / AGENTS：标注 Skillver P1–P5 已落地（匹配 → 实体公司 → seen → 详情 → 独立导出）；补充 `--match-report` 与 20/3 默认
- README / README.en：主路径改为 `--position-name` + `data/skillver/`；补充爬虫写 seen / 导出侧 seen；`raw`/`batches`/`--keywords-file` 标 legacy；附 58 标准岗设计表与导出用法
- AGENTS.md：标准岗抓取边界；catalog/seen 约定；legacy 勿当主路径
- `.gitignore`：确认忽略 `data/skillver/seen_jobs.json`（不忽略 catalog）
- 旧 keyword 批次结果挪至 `data/_legacy/{raw,batches}/`（不删用户数据）
- `.gitignore`：忽略 `seen_jobs.json`、`jobs/*` / `details/*` / `exports/*`（保留 `.gitkeep`）、`data/_legacy/`；不忽略 catalog
- README / README.en：Skillver 标准岗流水线设计与流程图（必须定岗、LLM 匹配+实体公司判断、最多 3 页凑 20 详情、`data/skillver/` 目录、seen 爬/导分写、独立导出脚本）

### 新增
- 独立岗位分析脚本 `scripts/job_analyze.py`：读取详情 JSON（可选列表 JSON 补充 skills），输出 Excel 明细/汇总、图表、Markdown 报告；可选从 `.env` 调用 DeepSeek（`deepseek-v4-pro`）生成文字总结。分析依赖见 `requirements-analyze.txt`，本地报告目录 `data/reports/` 已加入 `.gitignore`
- `job_analyze` 薪资图改为按区间中点分桶（默认步长 5K，`--salary-step` 可调）；Excel 同时保留「薪资原文」与「薪资区间」
- `job_analyze` 图表改版：去掉公司图；薪资用面积图且排除面议；学历甜甜圈；地区 lollipop（Top8+其他）；技能分产品/AI 双栏；JD Top10 极简条
- `job_analyze` Excel 明细精简为：职位/公司/薪资/地点(市·区)/经验学历/完整 JD；去掉薪资双列、活跃、技能标签、链接与 JD 截断
- `job_analyze` 可视化改为 Market Brief 单页海报：同时输出竖版手机 `poster_mobile.png` 与横版桌面 `poster_desktop.png`（薪资柔和柱+众数强调、学历比例条、地区 lollipop、技能双栏共用刻度、JD 词短线；面议排除、无公司图）
- `job_analyze` 自动识别日薪（`元/天`）与月薪（K），实习岗按日薪分桶（`--salary-day-step`，默认 50）
- `job_analyze` 修复海报中文乱码：强制绑定 Windows 雅黑/黑体字体文件，标题改用 bold 字体文件而非 fake-bold，规避 DejaVu 回退出 □
- `job_analyze` 支持应届+实习双轨：`--details-yingjie` / `--details-zaixiao`（可选 jobs），各自保留海报与 Excel，只调用一次 DeepSeek 生成可发群聊的短讯 `ai_summary.md`
- 详情前标题过滤：`--title-include` / `--title-exclude`，以及 `--title-filter-pm` 预设（保留「产品经理/产品运营」，排除工程师/开发/算法/销售等）；仅影响详情抓取，列表 JSON 仍保留原始搜索结果，避免 BOSS 宽召回浪费详情配额
- 批内多岗：`--keywords-file`（最多 8 个关键词）+ `--output-dir`，批内岗间默认随机等待 8–15 分钟（`--position-gap`）；批间休息由人工控制，命令结束不自动开下一批。示例批次文件见 `data/_legacy/batches/batch01.json`（legacy）
- 详情去重：仅按已成功抓取详情中的 `encrypt_job_id` 跳过重复开页（扫描 `boss_details_*.json` / `--seen-details-dir`）；列表未开详情的岗位不进入去重集合，详情记录写入 `encrypt_job_id`
- 详情抓取前自动过滤猎头/人力资源中介列表卡片（`boss_title` 含「猎头」/`headhunt`，或 `company_industry` 为「人力资源服务」），再应用 `--max-details`；列表 JSON 仍保留原始结果，详情配额优先留给直招岗位
- 详情/列表结果新增独立字段 `boss_active_status`（如「今日活跃」「在线」）：列表兼容 `activeTimeDesc` 与 `bossOnline`（仅在线时映射为「在线」）；详情页从招聘者卡片解析更细粒度状态并优先保留；JD 正文仍剔除该行，不混入描述
- 新增 `--stop-chrome` 命令：抓取/分析完成后关闭 BOSS 专用 CDP Chrome（按 user-data-dir 精准匹配隔离 profile，不碰主 Chrome）；抓取命令新增 `--close-chrome` 选项，正常结束后自动收尾（默认关闭，异常退出不触发以保留登录态）。复用已有 `stop_cdp_chrome` 的安全匹配逻辑，补齐进程关闭/收尾链路的单元测试。（#26）
- 城市码表外置为 `data/city_codes.json`（全量 300+ 城市，覆盖一二三四五线），新增 `--list-cities [关键词]` 命令查看支持的城市；`resolve_city` 查询链改为「本地静态码表 → 运行时拉 BOSS 接口 → 9 位裸码兜底」。城市码表打进 wheel，`pip install` 用户也可用。（#24）

### 修复
- 城市解析先执行本地及在线码表的正反向映射，再接受未收录的 9 位裸城市码；未知城市名现在会在抓取前明确报错退出。在线城市接口同时校验业务 `code`，不再把 `code: 35` 等风控响应静默当作空码表
- 登录探测识别 BOSS 风控码 `code: 37`「您的环境存在异常」为限制状态（RESTRICTED），并对未知风控码按 message 关键字（环境存在异常、访问频繁、安全校验等）兜底识别；避免已登录但被风控/限流的用户被误判为「登录探测响应异常」而无法继续。（#33）
- 登录探测改为区分可用、未登录、限制、空结果和响应异常；每轮仅请求一次并采用有上限的退避等待，`code: 31` 等明确限制会立即停止。探测请求现已纳入全局请求预算，CLI 不再把风控或异常统一提示为未登录。（#31）
- 登录检查、列表/详情抓取和 smoke test 的临时标签页统一在后台创建，仅人工登录页置前，避免自动流程抢占前台焦点（#28）
- 详情页 JD 改为只提取“职位描述”区，并在登录墙、导航页或过短正文出现时拒绝写入，不再把整页 `body`、招聘者信息、公司介绍和推荐职位当作 JD
- 同步 BOSS 当前 `city.json` / `condition.json` 映射，修正城市码以及薪资、经验、学历筛选枚举漂移，并在内置城市表未命中时自动加载 BOSS `cityGroup.json` 支持更多城市中文名
- `scrape_details` 最终保存改用 `os.path.dirname(path) or "."`，`--detail-output` 传不带目录的裸文件名时不再抛 `FileNotFoundError`（与循环内及其它写文件处保持一致）
- 修正城市码：天津 `101030100`、沈阳 `101070100`（原均误用 `101060100`）
- `require_runtime_dependencies` 缺失依赖时同时提示 uv 和 pip 安装方式
- `--merge` 现在会合并旧详情并落盘到 `--detail-output`（之前只合并列表，详情丢失）
- API URL filter 改用 `urlencode`（原字符串拼接，filter 值含特殊字符会出错）

### 变更
- 平台支持声明改为 macOS + Linux（Windows 代码分支保留但未经实测，不再声称支持，避免过度承诺）
- `pyproject.toml` 删除空的 `[csv]` extra（csv 是标准库）
- SKILL.md 脚本路径解析改用 Python `os.path.realpath`（macOS 自带 `readlink` 无 `-f`）

### 新增
- `scripts/job_summary.py` 抓取后摘要脚本：读取已有 JSON，输出岗位聚合摘要和求职材料优化提示词
- `boss-summary` 命令行入口，便于打包安装后直接运行摘要脚本
- 抓取后摘要测试：覆盖 JSON 加载、聚合维度、提示词输出和项目边界
- 版本号一致性测试：校验脚本、pyproject.toml、SKILL.md、README.md 四处版本同步
- CONTRIBUTING.md 贡献指南

## v2.0.0 (2026-06)

### 新功能
- `--check` 环境检查（CDP 连通性、依赖、登录态）
- `--setup-chrome` 一键启动 Chrome CDP（持久隔离 profile）
- `--copy-login-state` 手动导入主 Chrome 的 Local State + Cookie 相关文件到隔离 profile
- `--reset-chrome-profile` 重建 BOSS 专用 Chrome profile
- `--setup-chrome` 默认等待 BOSS 登录完成，并确认接口返回明文薪资
- `--no-wait-login` / `--login-timeout` 控制 setup 登录等待
- 默认抓取结果保存到 `~/.boss-zhipin-scraper/job-result`
- 未传 `--city` 时默认搜索上海
- `--format csv` 同时导出列表 CSV 和详情 CSV
- `--merge` 合并多次抓取结果（去重）
- `--cdp-port` 自定义 CDP 端口（默认 9222）
- `--smoke-test` 用真实 Chrome/CDP 跑一次搜索 API smoke test，不写结果文件
- `--allow-dom-fallback` 显式允许 API 失败时降级 DOM 提取
- `--version` 查看版本号
- 登录态检测：未登录时给出明确提示
- 分析报告技术词动态提取（不再硬编码）
- 进度显示：`[2/3 页, 45/90 条]`

### 改进
- CDP WebSocket 消息过滤 + 超时重试（不再无限卡死）
- 详情页写入去重（中断重跑不重复）
- 请求频率保护（最多 10 页，全局 500 次上限）
- 清除所有 bare except，改为具体异常类型
- API 路径提取为常量，方便维护
- DOM fallback 标记为 deprecated
- DOM fallback 默认关闭，避免把字体反爬后的薪资写进结果
- API 错误行不再被当成职位数据处理
- 详情输出保留 `job_id`、`job_link` 和 `salary_source`
- 详情页访问会带上列表 API 返回的 `securityId` / `lid` 上下文
- `--input ... --analysis --no-detail` 会从 `--detail-output`、同目录同时间戳详情文件、默认结果目录最新详情文件中加载详情
- 登录态检测改为多关键词、多城市 probe，但仍要求接口返回明文薪资
- Linux / Windows 平台支持（Chrome 路径 + 隔离 profile）
- pyproject.toml 版本锁定依赖

### 安全
- 默认不软链接、不复制主 Chrome profile；首次启动也不自动导入主 Chrome 登录态，避免影响 Gmail/GitHub 等主浏览器登录态
- API URL 可配置（`API_JOB_LIST_PATH` 常量）

## v1.0.0 (2026-06)

### 初始版本
- Chrome CDP 抓取 BOSS直聘职位列表
- API 明文薪资（绕过字体反爬）
- 详情页 JD 抓取 + 技能标签提取
- 增量写入（异常退出不丢数据）
- 分析报告（薪资分布、经验要求、简历建议）
- 多维筛选（规模、融资、薪资、经验、学历、行业）
