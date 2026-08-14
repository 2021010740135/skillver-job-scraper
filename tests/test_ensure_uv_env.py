#!/usr/bin/env python3
"""Unit tests for uv bootstrap (no network, no Chrome)."""

from __future__ import annotations

import importlib.util
import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ensure_uv_env.py"


def load_module():
    spec = importlib.util.spec_from_file_location("ensure_uv_env", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


class EnsureUvEnvTests(unittest.TestCase):
    def setUp(self):
        self.mod = load_module()

    def test_skill_root_is_skill_directory(self):
        self.assertEqual(self.mod.skill_root(), ROOT)

    def test_which_uv_uses_shutil(self):
        with mock.patch.object(self.mod.shutil, "which", return_value="/usr/bin/uv"):
            self.assertEqual(self.mod.which_uv(), "/usr/bin/uv")

    def test_ensure_returns_true_when_already_in_venv(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            if os.name == "nt":
                vpy = root / ".venv" / "Scripts" / "python.exe"
            else:
                vpy = root / ".venv" / "bin" / "python"
            vpy.parent.mkdir(parents=True)
            vpy.write_text("", encoding="utf-8")
            with mock.patch.object(self.mod, "skill_root", return_value=root), \
                    mock.patch.object(self.mod, "running_in_skill_venv", return_value=True), \
                    mock.patch.dict(os.environ, {self.mod.ENV_READY: "1"}):
                self.assertTrue(self.mod.ensure_skill_env(reexec_if_needed=True))

    def test_uv_sync_retries_mirror_on_failure(self):
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append((cmd, kwargs.get("env", {}).get("UV_DEFAULT_INDEX")))
            if len(calls) == 1:
                return mock.Mock(returncode=1)
            return mock.Mock(returncode=0)

        with mock.patch.dict(os.environ, {"UV_INDEX_URL": "", "UV_DEFAULT_INDEX": ""}), \
                mock.patch.object(self.mod, "_run", side_effect=fake_run):
            self.assertTrue(self.mod.uv_sync("uv", ROOT))
        self.assertGreaterEqual(len(calls), 2)
        self.assertEqual(calls[1][1], self.mod.TUNA_INDEX)

    def test_reexec_sets_env_ready(self):
        captured = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            captured["env"] = kwargs.get("env")
            return mock.Mock(returncode=7)

        with mock.patch.object(self.mod, "_run", side_effect=fake_run):
            with self.assertRaises(SystemExit) as ctx:
                self.mod.reexec_with_uv("uv", ROOT)
        self.assertEqual(ctx.exception.code, 7)
        self.assertEqual(captured["env"][self.mod.ENV_READY], "1")
        self.assertEqual(captured["cmd"][:3], ["uv", "run", "--directory"])


if __name__ == "__main__":
    unittest.main()
