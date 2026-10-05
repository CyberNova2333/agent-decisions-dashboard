#!/usr/bin/env bash
# Agent Decisions Dashboard Launcher for Linux / macOS
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "========================================================"
echo "  Agent Decisions Dashboard: 决策台账服务启动中..."
echo "========================================================"
echo ""

python3 -m core.server "$@"
