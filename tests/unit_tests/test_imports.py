# SPDX-FileCopyrightText: 2026 Vericto S.A.S.
# SPDX-License-Identifier: Apache-2.0

import tomllib
from pathlib import Path

from llama_index.core.tools.tool_spec.base import BaseToolSpec

import llama_index.tools.vericto
from llama_index.tools.vericto import VerictoToolSpec, __all__

ROOT = Path(__file__).resolve().parents[2]

EXPECTED_ALL = [
    "FindingDict",
    "VerdictDict",
    "VerictoSQLDatabase",
    "VerictoToolSpec",
    "__version__",
    "verdict_to_dict",
]


def test_all_imports() -> None:
    assert sorted(EXPECTED_ALL) == sorted(__all__)


def test_every_name_resolves() -> None:
    for name in __all__:
        assert getattr(llama_index.tools.vericto, name) is not None


def test_class() -> None:
    names_of_base_classes = [b.__name__ for b in VerictoToolSpec.__mro__]
    assert BaseToolSpec.__name__ in names_of_base_classes


def test_version_matches_metadata() -> None:
    from importlib.metadata import version

    assert llama_index.tools.vericto.__version__ == version("llama-index-tools-vericto")


def test_llamahub_metadata_points_at_the_package() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    llamahub = pyproject["tool"]["llamahub"]
    assert llamahub["import_path"] == "llama_index.tools.vericto"
    for class_name in llamahub["class_authors"]:
        assert hasattr(llama_index.tools.vericto, class_name)


def test_namespace_packages_have_no_init() -> None:
    # llama_index and llama_index.tools are PEP 420 namespaces shared with every
    # other llama-index-* package: an __init__.py here would shadow them.
    assert not (ROOT / "llama_index" / "__init__.py").exists()
    assert not (ROOT / "llama_index" / "tools" / "__init__.py").exists()
