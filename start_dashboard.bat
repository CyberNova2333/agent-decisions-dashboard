@echo off
chcp 65001 > nul
title Agent Decisions Dashboard
cd /d "%~dp0"

echo ========================================================
echo   Agent Decisions Dashboard: 决策台账服务启动中...
echo ========================================================
echo.
python -m core.server %*

pause
