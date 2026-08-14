# 环境与登录（浏览器 CDP）

脚本：`scripts/chrome_cdp.py`

当前只支持 **Windows**。启动时先找 Edge，没有再用 Chrome。本机已登录的隔离浏览器是明文薪资接口的前提。专用 profile 默认：`~/.boss-zhipin-scraper/chrome-profile`（不碰主浏览器）。

## 命令

```bash
python3 scripts/chrome_cdp.py --check --cdp-port 9222
python3 scripts/chrome_cdp.py --setup-chrome --cdp-port 9222
# 可选：--login-timeout 300  --no-wait-login  --copy-login-state  --reset-chrome-profile
python3 scripts/chrome_cdp.py --stop-chrome --cdp-port 9222
python3 scripts/chrome_cdp.py --list-cities 上海
```

`--check` 顺序：有没有 uv → 没有则安装 → `uv sync` 到本 skill `.venv` → CDP → 登录。  
国内 PyPI 超时可设 `UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple`。不要 `pip install` 进系统 Python。

`--copy-login-state` 按同一顺序拷主浏览器 User Data：先 Edge，没有再用 Chrome。

## 成功判据

`--check` 报告 uv / `.venv` / CDP 就绪，且已检测到登录态。

## 人机闸门 `WAIT_LOGIN`

未登录：进入 **WAIT_LOGIN**，等用户回复「已登录」后再跑 `--check`。  
限流 / 验证码 / 风控 → **停止**并提示用户，不硬闯。  
抓完可 `--stop-chrome`（只关专用 profile，Edge / Chrome 都认）。

默认 `--cdp-port`：`9222`。`--login-timeout`：`300` 秒。
