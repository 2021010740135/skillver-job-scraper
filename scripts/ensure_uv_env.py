#!/usr/bin/env python3
"""Stdlib-only bootstrap: uv + this skill's .venv.

Does not import websocket-client or requests. Safe to run with a bare Python.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ENV_READY = "SKILLVER_UV_READY"
TUNA_INDEX = "https://pypi.tuna.tsinghua.edu.cn/simple"
ALIYUN_INDEX = "https://mirrors.aliyun.com/pypi/simple"


def _configure_stdio_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        if stream is None:
            continue
        reconfigure = getattr(stream, "reconfigure", None)
        if not callable(reconfigure):
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError, AttributeError):
            try:
                reconfigure(errors="replace")
            except (OSError, ValueError, AttributeError):
                pass


_configure_stdio_utf8()


def skill_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _augment_path() -> None:
    extras = [
        Path.home() / ".local" / "bin",
        Path(sys.executable).resolve().parent,
        Path(sys.executable).resolve().parent / "Scripts",
    ]
    parts = os.environ.get("PATH", "").split(os.pathsep)
    prepend = []
    for extra in extras:
        text = str(extra)
        if extra.is_dir() and text not in parts and text not in prepend:
            prepend.append(text)
    if prepend:
        os.environ["PATH"] = os.pathsep.join(prepend + parts)


def which_uv() -> str | None:
    _augment_path()
    found = shutil.which("uv")
    if found:
        return found
    home = Path.home()
    exe = "uv.exe" if os.name == "nt" else "uv"
    candidates = [
        home / ".local" / "bin" / exe,
        home / ".cargo" / "bin" / exe,
        Path(sys.executable).resolve().parent / exe,
        Path(sys.executable).resolve().parent / "Scripts" / exe,
    ]
    for path in candidates:
        if path.is_file():
            return str(path)
    return None


def venv_python(root: Path | None = None) -> Path:
    root = root or skill_root()
    if os.name == "nt":
        return root / ".venv" / "Scripts" / "python.exe"
    return root / ".venv" / "bin" / "python"


def running_in_skill_venv(root: Path | None = None) -> bool:
    root = root or skill_root()
    vpy = venv_python(root)
    if not vpy.is_file():
        return False
    try:
        return Path(sys.executable).resolve() == vpy.resolve()
    except OSError:
        return False


def _run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, **kwargs)


def install_uv() -> str | None:
    print("  未找到 uv，正在安装（用户级工具，不改系统 Python）...")
    pip_attempts = [
        [sys.executable, "-m", "pip", "install", "uv", "-i", TUNA_INDEX],
        [sys.executable, "-m", "pip", "install", "uv"],
    ]
    for cmd in pip_attempts:
        try:
            result = _run(cmd, timeout=180)
        except (subprocess.TimeoutExpired, OSError) as exc:
            print(f"  ⚠️ pip 安装 uv 失败: {exc}")
            continue
        if result.returncode == 0:
            found = which_uv()
            if found:
                print(f"  ✅ 已通过 pip 安装 uv: {found}")
                return found
    try:
        if os.name == "nt":
            result = _run(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-Command",
                    "irm https://astral.sh/uv/install.ps1 | iex",
                ],
                timeout=180,
            )
        else:
            result = _run(
                ["sh", "-c", "curl -LsSf https://astral.sh/uv/install.sh | sh"],
                timeout=180,
            )
    except (subprocess.TimeoutExpired, OSError) as exc:
        print(f"  ⚠️ 官方安装脚本失败: {exc}")
        return None
    if result.returncode != 0:
        return None
    found = which_uv()
    if found:
        print(f"  ✅ 已安装 uv: {found}")
    return found


def uv_sync(uv: str, root: Path | None = None) -> bool:
    root = root or skill_root()
    indexes: list[str | None] = []
    env_index = os.environ.get("UV_INDEX_URL") or os.environ.get("UV_DEFAULT_INDEX")
    if env_index:
        indexes.append(env_index)
    indexes.extend([None, TUNA_INDEX, ALIYUN_INDEX])
    seen: set[str] = set()
    for index in indexes:
        key = index or "__default__"
        if key in seen:
            continue
        seen.add(key)
        env = os.environ.copy()
        if index:
            env["UV_DEFAULT_INDEX"] = index
            print(f"  uv sync（镜像 {index}）...")
        else:
            print("  uv sync...")
        try:
            result = _run([uv, "sync"], cwd=str(root), env=env, timeout=300)
        except (subprocess.TimeoutExpired, OSError) as exc:
            print(f"  ⚠️ uv sync 失败: {exc}")
            continue
        if result.returncode == 0:
            print("  ✅ 项目 .venv 已就绪")
            return True
    print("  ❌ uv sync 失败。可设置 UV_INDEX_URL 为国内镜像后重试。")
    return False


def reexec_with_uv(uv: str, root: Path | None = None) -> None:
    root = root or skill_root()
    env = os.environ.copy()
    env[ENV_READY] = "1"
    cmd = [uv, "run", "--directory", str(root), "python", *sys.argv]
    print("  切换到项目 .venv 继续...")
    raise SystemExit(_run(cmd, env=env).returncode)


def ensure_skill_env(*, reexec_if_needed: bool = True) -> bool:
    """Make sure this skill's .venv exists. May re-exec and not return."""
    root = skill_root()
    if os.environ.get(ENV_READY) == "1" and running_in_skill_venv(root):
        return True
    uv = which_uv()
    if not uv:
        uv = install_uv()
    if not uv:
        print("  ❌ 无法安装 uv。请手动安装: https://docs.astral.sh/uv/getting-started/installation/")
        print(f"     或: {sys.executable} -m pip install uv -i {TUNA_INDEX}")
        return False
    print(f"  ✅ uv: {uv}")
    if not uv_sync(uv, root):
        return False
    if reexec_if_needed and not running_in_skill_venv(root):
        reexec_with_uv(uv, root)
    return True
