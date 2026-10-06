# Agent 操作指南

本指南用于让 Agent 读取当前结论、追加讨论、区分实现证据并确认写入。任务钩子只做读取与检查，不运行模型、不执行代码、不自动登记意见。

## 1. 确定目标并读取

从本仓库目录执行，或先在专用环境安装本包。把路径换成实际目标项目的配置文件：

```sh
python -m core.agent_hooks --config /path/to/dashboard.config.json before-task
python -m core.agent_hooks --config /path/to/dashboard.config.json before-task --module 存储层
python -m core.agent_hooks --config /path/to/dashboard.config.json before-task --topic adr-storage
```

输出是 JSON，包含 `active_decisions`、`rejected_proposals`、`pending_requirements`；其中 `content` 和 `discussion` 是完整记录。按模块匹配 section/object/function 子串；`--path` 匹配正文或 section 子串，不是代码依赖分析。特定议题不存在会报错，不会伪装成无约束。

暂缓和已替代议题不列入当前约束清单。指定 `--topic` 时另附 `requested_topic` 完整记录，因此可以追溯这些议题的状态、正文和轮次。

钩子先读取 `/api/status`，比较真实数据库和议题目录与指定配置，并要求一致性检查通过。可以用 `--url http://127.0.0.1:其他端口` 覆盖连接地址，目标目录校验仍生效。仅允许本机 HTTP，禁用代理和重定向。服务须由用户按项目流程启动；钩子不会启动、重建或修复数据。

## 2. 保存与重试

使用现有 HTTP API，不直接改数据库或 metadata.json。下面是追加意见的标准库示例；在执行 POST 前保存请求文件，以便响应丢失后原样重试：

```python
import json
import uuid
from pathlib import Path
from urllib.request import Request, urlopen

base = "http://127.0.0.1:8765"
topic_id = "adr-storage"
with urlopen(base + "/api/topic/" + topic_id) as response:
    topic = json.load(response)
request_data = {
    "expected_version": topic["version"],
    "request_id": str(uuid.uuid4()),
    "new_user_opinion": "用户本轮实际原话",
    "new_agent_reply": "本轮实际回应与验证证据",
    "commit_message": "追加存储议题讨论",
}
# 路径选在目标项目的本地临时目录，避免把原话或回执意外提交到公开仓库。
Path("request.json").write_text(json.dumps(request_data, ensure_ascii=False), encoding="utf-8")
req = Request(base + "/api/topic/" + topic_id + "/save",
              json.dumps(request_data).encode("utf-8"), {"Content-Type": "application/json"})
with urlopen(req) as response:
    receipt = json.load(response)
Path("receipt.json").write_text(json.dumps(receipt, ensure_ascii=False), encoding="utf-8")
```

只有在该操作获用户授权、原话与回应已确定时执行。示例中具体文本不是用户意见，不要原样登记进真实台账。独立新操作分配新 ID；超时重试读取之前保存的 request.json，不重新获取最新版本、不生成新 ID。相同键携带不同内容会被拒绝。

创建使用 `POST /api/topic/create`，传 `id`、`title`、可选 `content_override` 及状态。已有议题省略的字段保留原值；空字符串表示明确清空支持清空的字段。核验使用 `POST /api/topic/:id/verify`，传 `expected_version`、`request_id`、`impl_commit`、`verifier`、`test_summary` 和布尔 `mark_verified`；这只登记调用者提供的证据，服务不替你运行测试。

## 3. 核对写入结果

```sh
python -m core.agent_hooks --config /path/to/dashboard.config.json after-write --topic adr-storage --receipt /path/to/receipt.json
```

退出码为 0 表示台账回执、当前版本与一致性已通过检查；`git_committed` 单独表示是否真正提交 Git。Git 关闭、暂存区冲突或 Git 错误时也要如实报告对应字段。退出码为 2 表示检查未通过，错误 JSON 输出到 stderr；参数格式错误也为 2。

旧回执的版本已被后续写入替代时钩子会拒绝确认，不会替你回滚。删除议题、单议题恢复到未创建状态和全库恢复应单独读取历史与一致性报告，本钩子不把这些操作当作普通写入。

## 4. 可选宿主钩子

宿主只需在适当阶段运行上述命令并检查退出码，无需本项目定义新的 Agent 协议。任务开始读取 `before-task` 输出；成功写入后检查 `after-write` 输出。没有宿主支持时手动运行同样有效。

本仓库不附带会自动生效的用户级配置，不把“存在 AGENTS.md”视作已安装钩子。AGENTS.md 的自动发现取决于 Agent 宿主；其他工具可将此指南链接加入其项目规则。不得把每次读/写文件都变成新议题，也不得伪造用户同意来满足检查。

## 常见失败

| 情况 | 下一步 |
|---|---|
| 服务离线或目标目录不符 | 核对配置、端口与服务；不要连默认端口盲写 |
| `428` 缺版本 | 先读取目标议题，再准备独立请求 |
| `409` 冲突 | 读取最新状态，核对内容；保留原草稿和原始请求 |
| 文件/索引漂移 | 先确认权威文件、外部编辑和未完成请求；维护操作避免与服务并发 |
| 正文与记录模板冲突 | 按提示闭合代码围栏或将模板示例放入围栏，不能删掉原话绕过检查 |
| Git 未提交 | 报告实际原因；台账保存、Git 提交和推送是不同结果 |
