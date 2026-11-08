---
title: 快速入门
description: Agent Decisions Dashboard 是一个轻量级、面向多智能体（Multi-Agent）协作编程与复杂研发工程的**本地决策记录与审计台账服务**。
---

# 快速入门

Agent Decisions Dashboard 是一个轻量级、面向多智能体（Multi-Agent）协作编程与复杂研发工程的**本地决策记录与审计台账服务**。

## 解决的核心痛点

- **痛点 1**：多 Agent 协作时缺乏唯一的裁决与共识沉淀通道，对话轮次一长容易产生决策漂移
- **痛点 2**：历史结论零散分布在聊天上下文或日志中，无法作为后续代码审查与架构回归的直接依据
- **痛点 3**：传统文档容易与真实代码脱节，缺少带密码学校验与版本指纹的幂等审计依据

---

## 环境准备

Python 3.10+，无需任何复杂的外部数据库（原生采用 SQLite 单文件存储）。

---

## 快速安装与运行

```bash
# 1. 克隆并进入目录
git clone https://github.com/CyberNova2333/agent-decisions-dashboard.git
cd agent-decisions-dashboard

# 2. 启动本地台账服务（默认监听本地端口 8765）
python -m core.server

# 3. 提交一条决策记录
curl -X POST http://127.0.0.1:8765/api/decisions \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "代码托管平台与双端同步规范",
    "prompt": "将主要代码托管平台切换为 GitHub 个人主开发命名空间",
    "decision": "默认使用 GitHub noreply 邮箱及独立签名私钥，严禁凭证混用与泄露",
    "git_commit": true
  }'
```

---

## 接下来探索

- 深入了解系统内部流转：查阅 [系统架构与设计](/docs/architecture)
- 探索全部配置参数与高级场景：查阅 [配置与使用指南](/docs/configuration)
- 遇到问题排错：查阅 [常见问题与排错](/docs/faq)
