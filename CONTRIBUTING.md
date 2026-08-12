# 本地开发与贡献指南

感谢你对 boss-zhipin-scraper 的兴趣！本项目默认采用**本地开发优先**的工作方式：修 Bug、加功能和补文档都可以直接在当前本地工作区完成，不以 GitHub Issue、分支、提交、推送或 Pull Request 为前置条件。

## 行为准则

请保持友善、尊重。技术讨论对事不对人，不接受任何人身攻击或骚扰言论。

## 开发之前

- 先阅读 `AGENTS.md` 和相关 README，确认当前主路径与文件边界。
- 先检查本地工作树状态和相关 diff，保留已有修改，不覆盖、不回滚不属于当前任务的工作。
- 将相互独立的改动拆成清晰的本地工作单元，分别补测试和文档，避免职责混杂。
- 允许使用 `git status`、`git diff` 等只读命令保护现有工作。只有用户明确提出时，才创建 Issue、Fork、分支、提交、Push 或 Pull Request；这些操作都不是本地开发的前置条件。

## 开发环境

```bash
cd boss-zhipin-scraper
pip install -r requirements.txt          # 或 uv sync
python3 -m unittest tests.test_chrome_setup   # 跑测试，确保全绿
```

要求 Python 3.10+，依赖只有 `requests` 和 `websocket-client`。

## 代码规范

- **风格**：遵循 [PEP 8](https://peps.python.org/pep-0008/)，用 4 空格缩进、UTF-8、LF 换行。
- **异常处理**：不要用 bare `except:`，必须捕获具体异常类型（`requests.ConnectionError`、`json.JSONDecodeError` 等），项目现有的代码就是这么做的，请保持一致。
- **单文件原则**：核心逻辑都在 `scripts/boss_cdp_raw.py`，新增小工具函数也放这里，不要随手建新文件。
- **注释**：复杂逻辑要写注释（参考 `human_scroll` 的做法）；公开函数补 docstring。

## 测试要求

- 修了 Bug 或加功能，**必须补测试**。测试在 `tests/test_chrome_setup.py`，用标准库 `unittest`，通过 mock 掉 `requests`/`websocket`，**不需要真实 Chrome 或网络**。
- 完成本地修改前先跑通：

  ```bash
  python3 -m unittest tests.test_chrome_setup
  ```

- 涉及版本号改动，会触发 `VersionConsistencyTests`，确保 `scripts/boss_cdp_raw.py`、`pyproject.toml`、`SKILL.md`、`README.md` 四处版本一致。

## 可选的本地提交信息（Commit Message）

本地开发不要求必须创建提交。只有用户明确要求提交时，才使用 [Conventional Commits](https://www.conventionalcommits.org/) 格式，参考现有提交历史：

```
<type>: <简短描述，中文或英文均可>

feat: 新功能        例: feat: 详情页加过程日志
fix: 修 Bug         例: fix bug salary garbled characters
optimize: 优化      例: optimize(risk-control): 优化详情页进入方式
docs: 文档          例: docs: 更新 README 参数说明
refactor: 重构      例: refactor: API 路径提取为常量
test: 测试          例: test: 补城市码去重校验
chore: 杂项         例: chore: 升级依赖
```

## 本地开发流程

1. 检查当前工作树并识别已有修改的归属。
2. 阅读相关代码、测试和文档，先确认行为再修改。
3. 改代码并补全 mock 测试；不得依赖真实 Chrome 或网络。
4. 如果改了用户可见行为，同步更新中文 `README.md`；有意义的变更更新 `CHANGELOG.md`。不再维护 `README.en.md`。
5. 运行相关测试和语法检查，最后报告修改文件、验证结果和剩余限制。

本地分支、Git commit 以及所有 GitHub 操作均为可选项。除非用户在当前任务中明确要求，否则不要因为缺少 Issue、分支、提交、Push 或 PR 而暂停本地开发。

## 关于合规

本项目通过复用用户**本人已登录的浏览器**抓取公开可见的职位数据，用于个人求职分析。本地开发时请不要加入任何大规模、无节制请求或绕过平台安全校验的逻辑。请遵守目标网站的条款，对自己使用本工具的行为负责。

## 本地开发遇到问题

- 优先阅读 `AGENTS.md`、README、现有测试和报错信息。
- 无法确认需求边界时，直接向用户询问；不要求创建 GitHub Issue。

需要 Issue、分支、提交、Push 或 Pull Request 时，由用户另行明确提出。
