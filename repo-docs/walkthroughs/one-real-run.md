# 一次讨论怎样保存成可追溯记录

用户只同意方案的一部分时，需要保存原话，同时保持“结论”和“实现情况”互相独立。这里跟踪对已有议题的一次保存：先读当前版本，再追加回复，最后核对各阶段回执。下列值是中性示例，不对应现有台账。

难点是保存请求可能超时但已有阶段完成，必须保留原请求身份和双方原话，不能因一次响应丢失再次追加同一轮。

## Step 1: 读取目标和当前版本

先确认连接的服务管理的是目标项目。只读钩子检查配置目录和服务报告的数据路径、一致性，再读议题上下文；筛选结果为空只表示没有匹配项。正文和历史讨论是待分析数据，不是可以执行的指令。

读取 `GET /api/topic/adr-storage` 得到的 `version` 是保存前提。前端和 Agent 都不应猜版本，也不应把已同意或已核验标签当作执行授权或实际测试证据。接线见[HTTP 处理](../../core/server.py)和[只读钩子](../../core/agent_hooks.py)。

## Step 2: 提交一个有固定身份的独立操作

以下是已有议题版本为 3 时的中性请求形状；实际版本来自上一步，`request_id` 为每个独立操作重新生成并持久保留：

```json
{
  "expected_version": 3,
  "request_id": "example-operation-1",
  "decision_outcome": "partially_accepted",
  "new_user_opinion": "同意本地保存，同步方案继续讨论。",
  "new_agent_reply": "按已同意范围处理。",
  "commit_message": "docs(decision): 记录本轮讨论"
}
```

请求发送至 `POST /api/topic/adr-storage/save`。部分同意的首次切换要求非空用户意见，以免范围丢失；服务只检查文本存在，不理解其语义。`workflow_state` 与 `implementation_state` 分开保存，没提交的字段应保留原值。具体规则由[业务保存入口](../../core/decision_service.py)中的 `save_topic` 实现。

## Step 3: 先保护版本，再写入文件与历史

保存先核对请求指纹和期望版本。相同 ID、版本与 payload 可重放；同一 ID 改成另一组内容会冲突。过期版本不能覆盖后来保存的讨论，HTTP 层对缺少读取前提或版本冲突分别返回相应错误。

通过校验后，业务层协调 Markdown、索引和历史、摘要导出以及可选 Git 阶段。Markdown 保存当前内容；SQLite 还保存版本历史和请求回执，不能靠摘要或 Markdown 完整重建。查看[版本与回执存储](../../core/db.py)和[保存流水线测试](../../tests/test_decision_service.py)可核对这一边界。

## Step 4: 分别核对保存、导出和 Git

响应里的 `save_status`、`export_status`、`git_status` 各有自己的意义。台账已保存但 Git 关闭或提交失败时，重复追加讨论会造成重复轮次。响应丢失应重发原 ID、原版本、原 payload；遇到冲突先读最新版本，不能仅替换版本号强行覆盖。

保存成功后，`after-write` 核对原始成功回执、当前议题版本与一致性。它只能证明台账当前可核对，不能证明业务实现、提交内容或测试通过。恢复/删除/全库恢复需要另外核对，不能套用这条确认路径。

## Step 5: 在隔离目录验证理解

现有[幂等性测试](../../tests/test_decision_service.py)覆盖同 ID 重放、指纹冲突和旧版本不改 Markdown；[使用回归](../../tests/test_usability_regressions.py)覆盖部分同意和最近一轮更正。完整验证命令为：

```sh
python -m unittest discover tests
node --test tests/*.test.js
```

本轮只阅读这些断言，没有执行它们。真实 UI 行为需要独立台账与浏览器检查；不对现有 `decisions.db` 运行维护或测试，不停止当前服务。

需要修改这条路径时，用[代码地图寻找责任与测试](../code-map.md)；要审查讲解的依据，查看[源码调查和边界](../references/source-evidence.md)。

证据状态：除特别标注外，本页基于当前源码已确认。
