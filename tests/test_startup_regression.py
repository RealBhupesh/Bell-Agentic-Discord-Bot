"""Startup regression: the bot module must import cleanly.

Guards against duplicate command registration (the `wipe` collision between
Message Wipe's hybrid command and the consent-game prefix command) and any
other module-level registration failure that unit tests miss because they
import submodules instead of the bot entry point.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_bot_module_imports_without_registration_errors():
    result = subprocess.run(
        [sys.executable, "-c", "import bot"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, (
        "importing bot failed at startup:\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )


def test_no_duplicate_command_names_or_aliases():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import bot\n"
                "seen = {}\n"
                "dupes = []\n"
                "for cmd in bot.bot.commands:\n"
                "    for name in [cmd.name, *cmd.aliases]:\n"
                "        if name in seen:\n"
                "            dupes.append((name, seen[name], cmd.qualified_name))\n"
                "        seen.setdefault(name, cmd.qualified_name)\n"
                "assert not dupes, dupes\n"
                "print(f'{len(list(bot.bot.commands))} commands registered, no duplicates')"
            ),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, (
        "duplicate command names/aliases detected:\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
