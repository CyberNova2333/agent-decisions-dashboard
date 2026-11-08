---
title: 配置与使用指南
description: Agent 决策面板 的参数配置详解、典型使用场景与最佳实践
---

# 配置与使用指南

### 基础配置

系统通过 `core/config.py` 或环境变量进行调度：

| 配置项 | 环境变量 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- |
| `SERVER_HOST` | `DECISION_HOST` | `127.0.0.1` | 本地服务监听地址，出于安全默认仅限回环 |
| `SERVER_PORT` | `DECISION_PORT` | `8765` | 服务监听端口 |
| `DB_PATH` | `DECISION_DB_PATH` | `.decisions/decisions.db` | 本地 SQLite 数据库存储路径 |
| `MARKDOWN_DIR`| `DECISION_MD_DIR` | `.decisions/ledgers/` | 自动导出的 Markdown 台账目录 |
| `AUTO_GIT` | `DECISION_AUTO_GIT` | `false` | 是否在记录决策后自动调用 Git 签名提交 |

### API 接口规范

- `POST /api/decisions`：写入新决策。入参支持 `topic`（主题）、`prompt`（原始需求）、`decision`（决议结论）、`git_commit`（是否触发 Git 归档）。返回带有全局唯一决策 ID 与 SHA-256 校验和的幂等回执。
- `GET /api/decisions`：只读检索历史决策列表，支持按标签、状态与时间范围分页查询。
- `GET /api/decisions/:id`：获取单条决策的完整上下文与关联 Git 提交信息。

---

## 生产部署建议

1. **环境变量保护**：切勿将包含真实密钥或 Token 的配置提交至版本库；
2. **优雅停机与超时**：建议将关键长任务的超时时限设置为合理范围，避免僵尸进程驻留；
3. **日志监控**：结合控制台输出建立定期检查机制，捕获潜在异常。
