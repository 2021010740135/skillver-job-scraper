#!/usr/bin/env python3
"""Browser / CDP CLI: --check, --setup-chrome, --stop-chrome, --list-cities."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.boss_common import (
    DEFAULT_CDP_PORT,
    DEFAULT_LOGIN_TIMEOUT,
    __version__,
    ensure_skill_env,
    list_cities,
    run_check,
    run_setup_chrome,
    run_stop_chrome,
)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=f"Skillver 浏览器 CDP v{__version__}",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument("--cdp-port", type=int, default=DEFAULT_CDP_PORT)
    p.add_argument("--check", action="store_true")
    p.add_argument("--setup-chrome", action="store_true")
    p.add_argument("--stop-chrome", action="store_true")
    p.add_argument("--list-cities", nargs="?", const="", default=None)
    p.add_argument("--copy-login-state", action="store_true")
    p.add_argument("--reset-chrome-profile", action="store_true")
    p.add_argument("--no-wait-login", action="store_true")
    p.add_argument("--login-timeout", type=int, default=DEFAULT_LOGIN_TIMEOUT)
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    if args.list_cities is not None:
        keyword = args.list_cities.strip() or None
        list_cities(keyword)
        sys.exit(0)
    if args.stop_chrome:
        sys.exit(run_stop_chrome())
    if args.check:
        sys.exit(run_check(cdp_port=args.cdp_port))
    if args.setup_chrome:
        if not ensure_skill_env(reexec_if_needed=True):
            sys.exit(1)
        sys.exit(
            run_setup_chrome(
                cdp_port=args.cdp_port,
                copy_login_state=args.copy_login_state,
                reset_profile=args.reset_chrome_profile,
                wait_login=not args.no_wait_login,
                login_timeout=args.login_timeout,
            )
        )
    print("请指定 --check / --setup-chrome / --stop-chrome / --list-cities")
    sys.exit(2)


if __name__ == "__main__":
    main()
