#!/bin/bash
# SPDX-FileCopyrightText: 2026 Vericto S.A.S.
# SPDX-License-Identifier: Apache-2.0
#
# The package itself imports llama_index.core and its own modules only, never
# another llama-index-* integration (an LLM, an embedding model, a reader): it
# must install with llama-index-core alone. Tests may use llama_index.core's
# mocks.
set -eu

if grep -rnE --include="*.py" "^\s*(from|import) llama_index\." llama_index \
    | grep -vE "(from|import) llama_index\.(core|tools\.vericto)([. ]|$)"; then
    exit 1
fi
