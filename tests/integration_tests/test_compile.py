# SPDX-FileCopyrightText: 2026 Vericto S.A.S.
# SPDX-License-Identifier: Apache-2.0

"""Test that the integration tests compile."""

import pytest


@pytest.mark.compile
def test_placeholder() -> None:
    """Used for compiling integration tests without running any real tests."""
