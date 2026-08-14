# 把本 skill 装到本机（给 Agent）

本机还没有本 skill 时先做这一步。不要另写安装脚本。拷完后用已有 `--check` 自举。

当前只支持 **Windows**。

## 要拷的文件

从本仓库 skill 根目录拷到用户 Agent 的 skills 目录（已有则覆盖同名文件）：

- `SKILL.md`
- `pyproject.toml`
- `uv.lock`
- `scripts/` 下全部 `.py`
- `references/` 下全部 `.md`
- `data/city_codes.json`
- `data/position_catalog.json`

不要拷：`data/<搜索词>/` 工作产物、`.venv`。`tests/` 仅开发需要。

## 落到哪

按用户正在用的 Agent，选一个已存在的 skills 根，再在下面建 `skillver-job-scraper/`：

- Hermes：`%USERPROFILE%\.hermes\skills\`
- Cursor：`%USERPROFILE%\.cursor\skills\`
- 用户指定的其它 skills 目录

用户已经在仓库里打开本 skill 时，不必再拷，直接进入 `--check`。

## 拷完后

在 skill 根目录执行：

```
python scripts/chrome_cdp.py --check --cdp-port 9222
```

国内 PyPI 超时可先设 `UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple`。

成功：uv、`.venv`、CDP、登录态都过。CDP 不通则按 `chrome-setup.md` 跑 `--setup-chrome`，进入 `WAIT_LOGIN`。

失败则停。不要改用系统 `pip install`，不要发明安装脚本。
