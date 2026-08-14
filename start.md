# Skillver 职位采集 · 安装契约

> **唯一权威安装契约**：规定 Agent 如何把本仓库安装为可用的 agent skill，
> 以及哪些环节**禁止**自动化。

| 项           | 值                                            |
| ------------ | --------------------------------------------- |
| 适用范围     | 本仓库已完整克隆到本机后的 skill 安装         |
| 触发方式     | 用户对 Agent 说：「根据 start.md 安装 skill」 |
| 最低系统要求 | Windows / macOS / Linux；无需预装 Python      |

---

## 1. 目的与范围

本文件是**唯一权威安装契约**：规定 Agent 如何把本仓库安装为可用的 agent skill，
以及哪些环节**禁止**自动化。

- **本契约覆盖**：环境自举（uv + 托管 CPython）、安全审计、版本一致性校验、
  文件复制、自包含虚拟环境、依赖安装、`--check` 验证。
- **本契约不覆盖**：登录、CSV 核验——这两处人机闸门属于抓取流程，
  安装阶段不涉及。

## 2. 术语与约定

| 术语               | 含义                                                       |
| ------------------ | ---------------------------------------------------------- |
| REPO               | 仓库根目录，即本文件所在目录                               |
| 托管解释器         | 由 uv 下载并管理的 CPython（位于 uv 专属目录，非系统安装） |
| 必须 / 应当 / 禁止 | 分别对应 MUST / SHOULD / MUST NOT（RFC 2119）              |

**硬性约定**：

- **禁止**使用系统/用户 Python——解释器一律来自 uv 托管目录（`--python-preference only-managed`）。
- **禁止**跳过安全审计（除非显式 `--skip-audit`）。
- **禁止**在安装阶段代替用户确认登录 / CSV 闸门。

## 3. 前置条件

1. 仓库已完整克隆：`SKILL.md`、`scripts/`、`data/`、`references/` 均存在。
2. 本文件（`start.md`）位于 REPO 根目录。
3. 网络可用（安装 uv、下载托管 CPython、拉取 pip 依赖需要）。

## 4. 安装流程

### 4.1 自举 uv（必须）

1. 检测 uv：`uv --version`，或检查 `~/.local/bin/uv`（Windows 为 `uv.exe`）是否存在。
2. 若缺失，用**系统自带工具**安装（uv 官方安装脚本为独立二进制，**无需 Python**）：

   ```bash
   # Windows（自带 PowerShell）
   powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"

   # macOS / Linux（自带 curl + sh）
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

3. 安装后复查 `uv --version`；仍失败则中止并向用户报告，不得继续。

> 说明：本机若已安装 uv（如 `C:\Users\<user>\.local\bin\uv.exe`），第 2 步自动跳过。

### 4.2 准备安装脚本（应当）

将下方「附录 A」中 `<!-- BEGIN INSTALL SCRIPT -->` 与 `<!-- END INSTALL SCRIPT -->`
之间的内容**原样提取**为 `<REPO>/install_skill.py`。

建议用 uv 托管解释器执行提取（保持全程不使用系统 Python）：

```bash
# Windows / macOS / Linux 通用（uv 托管 Python 执行）
uv run --python 3.13 --python-preference only-managed python -c "
import re, pathlib
t = pathlib.Path('start.md').read_text(encoding='utf-8')
# 标记须独占一行（行首即 <!-- BEGIN/END INSTALL SCRIPT -->）
m = re.search(r'^\s*<!-- BEGIN INSTALL SCRIPT -->\s*\n(.*?)^\s*<!-- END INSTALL SCRIPT -->\s*$', t, re.S | re.M)
assert m, 'marker not found in start.md'
body = m.group(1).strip()
lines = body.splitlines()
if lines and lines[0].strip().startswith(chr(96)*3):
    lines = lines[1:]
if lines and lines[-1].strip().startswith(chr(96)*3):
    lines = lines[:-1]
pathlib.Path('install_skill.py').write_text('\n'.join(lines) + '\n', encoding='utf-8')
print('extracted -> install_skill.py')
"
```

### 4.3 运行安装（必须）

```bash
uv run --python 3.13 --python-preference only-managed install_skill.py --repo .
```

- 脚本默认从 REPO 自动定位仓库根；在别处运行需 `--repo <绝对路径>`。
- 脚本**幂等**：重复执行会覆盖旧版本文件，不会重复安装依赖。
- 安装成功判据：退出码 `0`，且步骤 `[5/5]` 输出 `--check` 结果。
- 安装完成后，Agent 必须向用户汇报：安装结果摘要 + 目标目录绝对路径。

### 4.4 脚本执行步骤与判据

| 步骤   | 动作                                                            | 失败行为                                           |
| ------ | --------------------------------------------------------------- | -------------------------------------------------- |
| 1/5    | 安全审计（扫描捆绑 `.py` 风险模式）                             | P0 命中 → 中止，退出码 1                           |
| 2/5    | 版本一致性（SKILL.md / pyproject.toml / `__version__` / README）| 不一致 → 警告，不阻断                               |
| 3/5    | 环境检测（WorkBuddy / Hermes / 其他）                           | 无法识别 → 询问用户，不猜测                         |
| 3/5-b  | uv 自举（检测 → 缺失则安装）                                   | 安装失败 → 中止                                     |
| 4/5    | 复制 8 个清单文件到目标目录                                     | 缺源文件 → 中止                                     |
| 5/5    | 托管解释器 + `uv venv` + 依赖安装 + `--check`                   | 依赖装不上 → 中止；`--check` 未全绿 → 提示不阻断    |

**退出码约定**：`0` 成功；`1` 失败；`2` 参数错误（由 argparse 产生）。

### 4.5 命令行参数

| 参数              | 说明                                                                 |
| ----------------- | -------------------------------------------------------------------- |
| `--repo <路径>`   | 仓库根目录（默认：脚本所在目录含 start.md 时自动定位，否则当前目录） |
| `--target <目录>` | 强制安装目录，跳过环境检测                                           |
| `--skip-audit`    | 跳过安全审计（不推荐）                                               |
| `--dry-run`       | 只执行审计/版本/环境检测，不写入任何文件                             |

## 5. 人机闸门（禁止自动化）

| 闸门      | 规则                                                                   |
| --------- | ---------------------------------------------------------------------- |
| 登录      | `--check` 显示未登录 → 必须停下，等用户回复「已登录」后重跑 `--check` |
| CSV 核验  | 属于抓取流程，安装阶段不涉及；不得代替用户确认                         |

## 6. 安装后验证清单

Agent 汇报前应逐项确认：

- [ ] 退出码为 0
- [ ] 目标目录存在 8 个清单文件
- [ ] `.venv/pyvenv.cfg` 的 `home` 指向 uv 托管目录（非系统 Python）
- [ ] `.venv` 内 `python -c "import requests, websocket"` 成功
- [ ] `--check` 输出已转述给用户（含未登录提示）

## 7. 故障排查

| 现象                                       | 原因                                  | 处理                                                               |
| ------------------------------------------ | ------------------------------------- | ------------------------------------------------------------------ |
| `uv run` 找不到 `--python-preference` 参数 | uv 版本过旧                           | 升级 uv：`uv self update`                                          |
| `only-managed` 找不到解释器                | 未执行托管解释器下载                  | 脚本会自动 `uv python install 3.13`；手动：`uv python install 3.13` |
| pip 源超时                                 | 网络/镜像问题                         | 脚本自动回退：默认 → pypi.org → 清华镜像                           |
| `--check` 未全绿且提示登录                 | BOSS 未登录或 CDP 未启动              | 运行 `scripts/boss_cdp_raw.py --setup-chrome` 登录后重跑 `--check`  |
| 目标目录被识别为 Hermes                    | 机器上同时有 `.workbuddy` 与 `.hermes`| 用 `--target` 显式指定                                              |

## 8. 卸载

```bash
# WorkBuddy
rm -rf ~/.workbuddy/skills/skillver-job-scraper

# Hermes / Claude Code
rm -rf ~/.hermes/skills/data-science/skillver-job-scraper
```

卸载仅删除 skill 包本体；REPO 内的 `.venv` 与 `data/skillver/` 工作数据不受影响。

---

## 附录 A：安装脚本

<!-- BEGIN INSTALL SCRIPT -->

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""skillver-job-scraper 一键安装脚本（内嵌于 start.md）。

用法（统一用 uv 运行，Python 只来自 uv 托管目录）:
    uv run --python 3.13 --python-preference only-managed install_skill.py
    uv run --python 3.13 --python-preference only-managed install_skill.py --repo .

可选:
    --target <目录>    强制安装目录（跳过环境检测）
    --skip-audit       跳过安全审计
    --dry-run          只做检查，不写任何文件

退出码: 0=成功, 1=失败, 2=参数错误。
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

SKILL_NAME = "skillver-job-scraper"
CDP_PORT = 9222
UV_INSTALL_URL = "https://astral.sh/uv/install.ps1"  # Windows
UV_INSTALL_SH = "https://astral.sh/uv/install.sh"    # macOS / Linux
UV_LOCAL_DIR = Path.home() / ".local" / "bin"
PYTHON_VERSION = "3.13"

# 需要复制进 skill 包的文件（相对 REPO 根）
FILE_MANIFEST = [
    "SKILL.md",
    "requirements.txt",
    "scripts/boss_cdp_raw.py",
    "scripts/export_skillver_csv.py",
    "data/city_codes.json",
    "data/skillver/position_catalog.json",
    "data/skillver/position_aliases.json",
    "references/classify-decisions.md",
]

# uv pip 源回退顺序（None = 默认源）
PIP_INDEXES = [None, "https://pypi.org/simple", "https://pypi.tuna.tsinghua.edu.cn/simple"]

# (正则, 级别, 说明) —— P0 命中立即中止；P1 仅提示
RISK_PATTERNS = [
    (r"\beval\s*\(", "P0", "eval 动态执行"),
    (r"\bexec\s*\(", "P0", "exec 动态执行"),
    (r"pickle\.loads", "P0", "pickle 反序列化"),
    (r"os\.system\s*\(", "P1", "os.system 命令执行"),
    (r"shell\s*=\s*True", "P1", "subprocess shell=True"),
    (r"base64\.b64decode", "P1", "base64 解码"),
]


def log_ok(msg: str) -> None:
    print(f"  [OK]   {msg}")


def log_warn(msg: str) -> None:
    print(f"  [WARN] {msg}")


def log_err(msg: str) -> None:
    print(f"  [ERR]  {msg}")


def venv_python(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def find_uv() -> str | None:
    """定位 uv 可执行文件：PATH 优先，其次 ~/.local/bin。"""
    for exe in ("uv", "uv.exe"):
        p = shutil.which(exe)
        if p:
            return p
    uv_local = UV_LOCAL_DIR / ("uv.exe" if os.name == "nt" else "uv")
    if uv_local.exists():
        return str(uv_local)
    return None


def install_uv() -> str | None:
    """全局安装 uv（用户级 ~/.local/bin，非系统级）。"""
    log_ok("未检测到 uv，开始全局安装 ...")
    try:
        if os.name == "nt":
            cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                   "-Command", f"irm {UV_INSTALL_URL} | iex"]
        else:
            cmd = ["sh", "-c", f'curl -LsSf "{UV_INSTALL_SH}" | sh']
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        if r.returncode != 0:
            log_err(f"uv 安装失败: {r.stderr[-500:] or r.stdout[-500:]}")
            return None
    except Exception as e:
        log_err(f"uv 安装异常: {e}")
        return None
    uv = find_uv()
    if uv:
        log_ok(f"uv 已安装: {uv}")
        return uv
    log_err("uv 安装完成但未找到可执行文件，请手动安装: https://docs.astral.sh/uv/")
    return None


def detect_target(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).expanduser()
    home = Path.home()
    wb_skills = home / ".workbuddy" / "skills"
    hm_skills = home / ".hermes" / "skills"
    if wb_skills.exists():
        target = wb_skills / SKILL_NAME
        log_ok(f"检测到 WorkBuddy，目标目录: {target}")
        return target
    if hm_skills.exists():
        target = hm_skills / "data-science" / SKILL_NAME
        log_ok(f"检测到 Hermes/Claude Code，目标目录: {target}")
        return target
    target = wb_skills / SKILL_NAME
    log_warn(f"未识别平台，默认按 WorkBuddy 目录安装: {target}")
    return target


def audit_bundle(repo: Path) -> bool:
    """扫描捆绑 .py 的风险模式。返回 True 表示应中止。"""
    p0_hits: list[str] = []
    p1_hits: list[str] = []
    for rel in FILE_MANIFEST:
        if not rel.endswith(".py"):
            continue
        p = repo / rel
        if not p.exists():
            log_err(f"缺少文件: {rel}")
            return True
        text = p.read_text(encoding="utf-8", errors="ignore")
        for pat, level, desc in RISK_PATTERNS:
            if re.search(pat, text):
                (p0_hits if level == "P0" else p1_hits).append(f"{rel}: {desc}")
    for h in p1_hits:
        log_warn(f"P1 {h}（已知抓取功能所需，放行）")
    if p0_hits:
        for h in p0_hits:
            log_err(f"P0 {h}")
        return True
    log_ok("安全审计通过（无 P0 风险模式）")
    return False


def check_versions(repo: Path) -> None:
    versions: dict[str, str] = {}
    sk = (repo / "SKILL.md").read_text(encoding="utf-8", errors="ignore")
    m = re.search(r"^version:\s*([\d.]+)", sk, re.M)
    if m:
        versions["SKILL.md"] = m.group(1)
    py = (repo / "pyproject.toml").read_text(encoding="utf-8", errors="ignore")
    m = re.search(r'^version\s*=\s*"([\d.]+)"', py, re.M)
    if m:
        versions["pyproject.toml"] = m.group(1)
    bf = (repo / "scripts" / "boss_cdp_raw.py").read_text(encoding="utf-8", errors="ignore")
    m = re.search(r'__version__\s*=\s*"([\d.]+)"', bf)
    if m:
        versions["boss_cdp_raw.py"] = m.group(1)
    rd = (repo / "README.md").read_text(encoding="utf-8", errors="ignore")
    # 只匹配 README 首个标题行中的版本（如 "# Skillver 职位采集 · Agent Skill v2.5.1"）
    m = re.search(r"^# .*?v?(\d+\.\d+\.\d+)", rd, re.M)
    if m:
        versions["README.md"] = m.group(1)
    uniq = set(versions.values())
    if len(uniq) > 1:
        log_warn(f"版本不一致: {versions}")
    else:
        log_ok(f"版本一致: {list(versions.values())[0] if versions else '未检出'}")


def copy_manifest(repo: Path, target: Path) -> bool:
    for rel in FILE_MANIFEST:
        src, dst = repo / rel, target / rel
        if not src.exists():
            log_err(f"缺少源文件: {src}")
            return False
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    log_ok(f"已复制 {len(FILE_MANIFEST)} 个文件到 {target}")
    return True


def ensure_managed_python(uv: str) -> bool:
    """确保 uv 托管解释器存在（不用系统 Python）。"""
    r = subprocess.run(
        [uv, "python", "find", "--python-preference", "only-managed", PYTHON_VERSION],
        capture_output=True, text=True)
    if r.returncode == 0:
        log_ok(f"uv 托管解释器已就绪: {r.stdout.strip()}")
        return True
    log_ok(f"下载 uv 托管 CPython {PYTHON_VERSION}（不依赖系统 Python）...")
    r = subprocess.run([uv, "python", "install", PYTHON_VERSION],
                       capture_output=True, text=True)
    if r.returncode != 0:
        log_err(f"uv 托管解释器下载失败: {r.stderr[-500:] or r.stdout[-500:]}")
        return False
    log_ok("uv 托管解释器安装完成")
    return True


def setup_venv(repo: Path, uv: str) -> Path | None:
    """用 uv 创建自包含 venv：解释器来自 uv 托管目录，不链接系统 Python。"""
    if not ensure_managed_python(uv):
        return None
    venv = repo / ".venv"
    py = venv_python(venv)
    if not py.exists():
        log_ok("用 uv 创建自包含 .venv（强制 only-managed，绝不使用系统 Python）...")
        r = subprocess.run(
            [uv, "venv", str(venv), "--python", PYTHON_VERSION,
             "--python-preference", "only-managed"],
            capture_output=True, text=True)
        if r.returncode != 0:
            log_err(f"uv venv 创建失败: {r.stderr[-500:] or r.stdout[-500:]}")
            return None
        log_ok("uv venv 创建完成（解释器来自 uv 托管目录）")
    ok = False
    for idx in PIP_INDEXES:
        cmd = [uv, "pip", "install", "--python", str(py), "-r", str(repo / "requirements.txt")]
        if idx:
            cmd += ["--index-url", idx]
        log_ok(f"uv pip 安装（{'默认源' if idx is None else idx}）...")
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode == 0:
            ok = True
            break
        log_warn(f"源失败: {(r.stderr or r.stdout)[-200:]}")
    if not ok:
        log_err("依赖安装失败，所有源均不可用")
        return None
    log_ok("依赖安装完成（venv 内，未触碰系统 Python）")
    return py


def run_check(py: Path, repo: Path) -> bool:
    cmd = [str(py), str(repo / "scripts" / "boss_cdp_raw.py"), "--check", "--cdp-port", str(CDP_PORT)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    out = (r.stdout or "") + (r.stderr or "")
    print(out.strip()[-1200:])
    if r.returncode == 0:
        log_ok("--check 全绿")
        return True
    log_warn("--check 未全绿（常见：BOSS 未登录）。依赖与脚本已就绪，登录后重跑 --check 即可。")
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description="skillver-job-scraper 一键安装")
    ap.add_argument("--repo", default=".", help="仓库根目录（含 start.md）")
    ap.add_argument("--target", default=None, help="强制安装目录")
    ap.add_argument("--skip-audit", action="store_true", help="跳过安全审计")
    ap.add_argument("--dry-run", action="store_true", help="只检查，不写入")
    args = ap.parse_args()

    # REPO 定位优先级：--repo 显式 > 脚本所在目录（临时文件放在仓库根）> 当前目录
    if args.repo and args.repo != ".":
        repo = Path(args.repo).expanduser().resolve()
    else:
        script_dir = Path(__file__).resolve().parent
        if (script_dir / "start.md").exists():
            repo = script_dir
        else:
            repo = Path.cwd().resolve()
    if not (repo / "start.md").exists():
        log_err(f"{repo} 下未找到 start.md，请用 --repo 指定仓库根目录")
        return 1
    log_ok(f"仓库: {repo}")

    print("\n[1/5] 安全审计")
    if args.skip_audit:
        log_warn("已跳过审计 (--skip-audit)")
    elif audit_bundle(repo):
        log_err("审计发现 P0 风险，中止安装")
        return 1

    print("\n[2/5] 版本一致性")
    check_versions(repo)

    print("\n[3/5] 环境检测")
    target = detect_target(args.target)

    # uv 是运行时隔离的基础：缺失则全局安装（不需要系统 Python）
    print("\n[3/5] uv 运行时")
    uv = find_uv()
    if uv is None:
        uv = install_uv()
        if uv is None:
            return 1
    log_ok(f"使用 uv: {uv}")

    if args.dry_run:
        log_ok("dry-run：以上检查通过，未写入任何文件")
        return 0

    print("\n[4/5] 复制文件")
    if not copy_manifest(repo, target):
        return 1

    print("\n[5/5] 依赖与验证")
    py = setup_venv(repo, uv)
    if py is None:
        return 1
    run_check(py, repo)

    print()
    log_ok(f"安装完成: {target}")
    print("  下次直接对 Agent 说：使用 Skillver 职位采集 skill 抓取 <岗位>")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

<!-- END INSTALL SCRIPT -->
