# SPDX-FileCopyrightText: 2026 Vericto S.A.S.
# SPDX-License-Identifier: Apache-2.0

"""Release gate: the tag matches the version, and no development-only override remains.

Usage: python scripts/check_release.py v0.1.0
"""

import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main(tag: str) -> int:
    """Return 0 when the package may be released under `tag`."""
    version_file = (ROOT / "llama_index" / "tools" / "vericto" / "_version.py").read_text(
        encoding="utf-8"
    )
    match = re.search(r'^__version__ = "([^"]+)"$', version_file, re.MULTILINE)
    if match is None:
        print("no __version__ in llama_index/tools/vericto/_version.py")
        return 1
    errors = []
    if tag != f"v{match.group(1)}":
        errors.append(f"tag {tag} does not match __version__ {match.group(1)}")
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    uv = pyproject.get("tool", {}).get("uv", {})
    if uv.get("override-dependencies") or uv.get("sources"):
        errors.append(
            "[tool.uv] still has override-dependencies or sources: the tests ran against "
            "something other than the published dependencies. Remove them and run `uv lock`."
        )
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    heading = re.search(rf"^## \[{re.escape(match.group(1))}\] - (\S+)$", changelog, re.MULTILINE)
    if heading is None or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", heading.group(1)):
        errors.append(f"CHANGELOG.md needs a dated section: ## [{match.group(1)}] - YYYY-MM-DD")
    for error in errors:
        print(error)
    return 1 if errors else 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
