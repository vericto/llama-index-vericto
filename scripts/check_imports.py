# SPDX-FileCopyrightText: 2026 Vericto S.A.S.
# SPDX-License-Identifier: Apache-2.0

"""Check that the given files can be imported (as in LangChain's partner packages)."""

import importlib.util
import sys
import traceback


def main(files: list[str]) -> int:
    """Import every file; return 1 if any of them fails."""
    failed = False
    for index, file in enumerate(files):
        try:
            spec = importlib.util.spec_from_file_location(f"_check_{index}", file)
            if spec is None or spec.loader is None:
                msg = f"cannot load {file}"
                raise ImportError(msg)
            spec.loader.exec_module(importlib.util.module_from_spec(spec))
        except Exception:
            failed = True
            print(file)
            traceback.print_exc()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
