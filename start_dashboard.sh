#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-only
# This file is part of Agent Decisions Dashboard and is licensed under GNU AGPLv3 with Additional Terms (see LICENSE and ADDITIONAL_TERMS.zh-CN.md; ref: ADDITIONAL_TERMS.en.md).
# Agent Decisions Dashboard Launcher for Linux / macOS
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "========================================================"
echo "  Agent Decisions Dashboard: 决策台账服务启动中..."
echo "========================================================"
echo ""

python3 -m core.server "$@"
