import type { ApiCatalogSpec } from './api-types'

export const apiSpecZh: ApiCatalogSpec = {
  project: 'Agent Decisions Dashboard · API 与组件参考',
  subtitle:
    '覆盖全部回环 HTTP 端点、CAS 事务写操作与只读 Agent 钩子组件。所有接口强制回环监听与 10 MiB 请求上限。',
  environments: [
    { label: '本机回环默认', value: 'http://127.0.0.1:8765' },
    { label: 'Localhost 别名', value: 'http://localhost:8765' },
  ],
  searchPlaceholder: '搜索端点路径、CLI 命令或关键词…',
  emptyText: '没有匹配的端点或组件，请尝试更换筛选分组或关键词。',
  labels: {
    allGroups: '全部',
    canDo: '✅ 能做到',
    cannotDo: '⛔ 明确限制 / 拒绝条件',
    params: '输入参数与约束',
    paramName: '字段 / 参数',
    paramLocation: '位置',
    paramType: '类型',
    paramRequired: '必填',
    paramDesc: '说明与校验规则',
    responses: '响应状态与退出码契约',
    examples: '标准调用示例',
    responseSample: '标准返回示例',
    copy: '复制',
    copied: '已复制',
    noParams: '该接口无需额外请求参数。',
    required: '必填',
    optional: '可选',
    deepDocs: '查看契约详解',
    totalItems: '项接口/组件',
    envLabel: '请求基址切换',
    mobilePicker: '选择接口或组件',
    defaultLabel: '默认',
  },
  groups: [
    { id: 'query', title: '只读查询 HTTP' },
    { id: 'write', title: '事务写入与恢复 POST' },
    { id: 'agent', title: 'Agent 钩子与协议' },
  ],
  items: [
    {
      id: 'get-api-status',
      group: 'query',
      kind: 'GET',
      title: '服务状态与一致性预检',
      signature: 'GET /api/status',
      auth: '本机回环',
      stability: '只读',
      summary:
        '返回当前服务挂载的项目名称、真实绝对数据路径（decisions_dir、database_path、metadata_json_path）、Git 可用性以及一致性摘要；是 agent_hooks 防写错实例的预检入口。',
      capabilities: [
        '核实运行中的端口对应的真实磁盘目录，避免写入示例仓库',
        '返回一致性状态 consistency，提前暴露索引或 Markdown 漂移',
      ],
      limitations: [
        '仅绑定回环地址（127.0.0.1 / localhost），不支持远程公网直接探活',
        '不触发目录写操作，也不自动修复不一致',
      ],
      params: [],
      responses: [
        {
          status: '200 OK',
          tone: 'ok',
          summary: '返回项目标识、绝对路径、Git 状态及一致性摘要 JSON',
          example: `{
  "project_name": "Agent Decisions Dashboard",
  "decisions_dir": "/path/to/decisions",
  "database_path": "/path/to/decisions.db",
  "metadata_json_path": "/path/to/decisions/metadata.json",
  "git_available": true,
  "consistency": { "ok": true, "mismatches": [] }
}`,
        },
      ],
      examples: [
        {
          label: 'curl',
          code: `curl -s {{BASE_URL}}/api/status`,
        },
        {
          label: 'Python',
          code: `import json, urllib.request
with urllib.request.urlopen("{{BASE_URL}}/api/status") as r:
    status = json.load(r)
print(status["decisions_dir"], status["consistency"])`,
        },
      ],
      relatedLink: '/docs/contracts',
      relatedLabel: '查看 HTTP REST API 规范',
    },
    {
      id: 'get-api-topics',
      group: 'query',
      kind: 'GET',
      title: '议题列表与治理摘要',
      signature: 'GET /api/topics',
      auth: '本机回环',
      stability: '只读',
      summary:
        '返回受 topic_scope.active_topic_ids 过滤的议题清单、三轴状态、settled_decisions、open_questions 与配置元数据。',
      capabilities: [
        '按 topic_scope 自动收敛列表，隔离历史迁出议题',
        '一次返回看板双栏所需的概览、未决问题与生命周期定义',
      ],
      limitations: [
        '被 topic_scope 排除的历史议题不会出现在此列表（需用 GET /api/topic/<id> 直查）',
        '不返回单议题完整正文与全部多轮 discussion 历史',
      ],
      params: [],
      responses: [
        {
          status: '200 OK',
          tone: 'ok',
          summary: '返回 filtered topics 列表与治理统计',
          example: `{
  "topics": [{ "id": "adr-storage", "title": "存储选型", "workflow_state": "decided", "decision_outcome": "accepted", "version": 3 }],
  "settled_decisions": ["adr-storage"],
  "open_questions": []
}`,
        },
      ],
      examples: [
        {
          label: 'curl',
          code: `curl -s {{BASE_URL}}/api/topics`,
        },
        {
          label: 'JavaScript',
          code: `const res = await fetch('{{BASE_URL}}/api/topics');
const data = await res.json();`,
        },
      ],
      relatedLink: '/docs/contracts',
    },
    {
      id: 'get-api-topic-detail',
      group: 'query',
      kind: 'GET',
      title: '单议题完整详情与快照',
      signature: 'GET /api/topic/{id}',
      auth: '本机回环',
      stability: '只读',
      summary:
        '按可移植 ID 查询单议题完整 Markdown 内容、当前版本号 version、逐轮 discussion 历史及最近 SQLite revisions。即使已被 topic_scope 过滤的旧议题仍可直达。',
      capabilities: [
        '获取写入 /save 前必需的当前 expected_version 乐观锁版本',
        '包含最近历史快照列表 rev_id，便于审阅或单议题恢复',
      ],
      limitations: [
        'id 必须符合 validate_portable_id（1-128 位 [a-zA-Z0-9_-]）',
        '已归档删除的议题返回 404（需从 /api/git/log 找 TOPIC_REMOVE 的 rev_id 恢复）',
      ],
      params: [
        {
          name: 'id',
          location: 'path',
          type: 'string',
          required: true,
          description: '合法议题 ID，拒绝 ..、路径分隔符与 Windows 设备保留名',
        },
      ],
      responses: [
        {
          status: '200 OK',
          tone: 'ok',
          summary: '返回完整议题正文、三轴状态、当前 version 与快照',
          example: `{
  "id": "adr-storage",
  "version": 3,
  "workflow_state": "decided",
  "decision_outcome": "accepted",
  "implementation_state": "in_progress",
  "discussion": []
}`,
        },
        { status: '404 Not Found', tone: 'err', summary: '议题不存在或已被归档删除' },
      ],
      examples: [
        {
          label: 'curl',
          code: `curl -s {{BASE_URL}}/api/topic/adr-storage`,
        },
      ],
      relatedLink: '/docs/contracts',
    },
    {
      id: 'get-api-agent-context',
      group: 'query',
      kind: 'GET',
      title: '五桶 Agent 上下文导出',
      signature: 'GET /api/agent/context',
      auth: '本机回环',
      stability: '只读',
      summary:
        '按 module、path 或 topic_id 返回严格区隔的五桶治理上下文（active_decisions、rejected_proposals、pending_requirements、deferred_topics、superseded_topics）。',
      capabilities: [
        '把 partially_accepted 转入 pending_requirements，防止 Agent 擅自扩大同意范围',
        '把 rejected 从 superseded 历史中隔离，仅当前有效否决进入红线',
      ],
      limitations: [
        '指定不存在的 topic_id 时直接报 404 错误，绝不静默返回空对象',
        '输出仅供辅助阅读与决策核对，不转化为任何命令执行权限',
      ],
      params: [
        { name: 'module', location: 'query', type: 'string', description: '按模块类别过滤上下文' },
        { name: 'path', location: 'query', type: 'string', description: '按相关源码路径过滤' },
        { name: 'topic_id', location: 'query', type: 'string', description: '聚焦单个议题并返回 requested_topic' },
        {
          name: 'format',
          location: 'query',
          type: '"json" | "markdown"',
          defaultValue: 'json',
          description: '指定返回结构化 JSON 或只读 Markdown 摘要',
        },
      ],
      responses: [
        {
          status: '200 OK',
          tone: 'ok',
          summary: '返回五桶上下文 JSON 或 Markdown 字符串',
          example: `{
  "active_decisions": [],
  "rejected_proposals": [],
  "pending_requirements": [],
  "deferred_topics": [],
  "superseded_topics": []
}`,
        },
        { status: '404 Not Found', tone: 'err', summary: '显式传入的 topic_id 不存在' },
      ],
      examples: [
        {
          label: 'curl (JSON)',
          code: `curl -s "{{BASE_URL}}/api/agent/context?module=存储层&format=json"`,
        },
        {
          label: 'curl (Markdown)',
          code: `curl -s "{{BASE_URL}}/api/agent/context?topic_id=adr-storage&format=markdown"`,
        },
      ],
      relatedLink: '/docs/contracts',
    },
    {
      id: 'post-api-topic-create',
      group: 'write',
      kind: 'POST',
      title: '新建议题与首版快照',
      signature: 'POST /api/topic/create',
      auth: 'Host + Origin + Sec-Fetch-Site',
      stability: '幂等写入',
      summary:
        '校验可移植 ID 与 JSON/Markdown 围栏格式后，写入权威 Markdown、SQLite 议题行与首版 REVISION 快照。',
      capabilities: [
        '强制检查 portable_id（拒绝大小写撞车）与 request_id 幂等去重',
        '响应分开返回 save_status、export_status 与 git_status',
      ],
      limitations: [
        '请求体超过 10 MiB 返回 413；非 application/json 或带 Transfer-Encoding 被拒绝',
        '首次即设为 partially_accepted 时必须提供用户原话，否则 400 拒绝',
      ],
      params: [
        { name: 'id', location: 'body', type: 'string', required: true, description: '1-128 位 [a-zA-Z0-9_-] 全局唯一 ID' },
        { name: 'title', location: 'body', type: 'string', required: true, description: '议题标题' },
        { name: 'request_id', location: 'body', type: 'string', required: true, description: 'UUID 幂等键（同键同参可重放）' },
        { name: 'workflow_state', location: 'body', type: 'string', defaultValue: 'pending', description: 'pending / discussing / decided / deferred / superseded' },
        { name: 'decision_outcome', location: 'body', type: 'string', defaultValue: '""', description: '空 / accepted / partially_accepted / rejected' },
      ],
      responses: [
        {
          status: '200 OK',
          tone: 'ok',
          summary: '创建成功或原样重放（is_replay: true）',
          example: `{
  "ok": true,
  "version": 1,
  "save_status": "saved",
  "export_status": "exported",
  "git_status": "committed"
}`,
        },
        { status: '400 Bad Request', tone: 'err', summary: 'ID 非法、围栏未闭合或缺少必填原话/否决理由' },
        { status: '409 Conflict', tone: 'warn', summary: '议题已存在或同 request_id 不同载荷冲突' },
      ],
      examples: [
        {
          label: 'curl',
          code: `curl -X POST "{{BASE_URL}}/api/topic/create" \\
  -H "Content-Type: application/json" \\
  -d '{
    "id": "adr-cache-policy",
    "title": "缓存失效策略",
    "request_id": "11111111-2222-4333-8444-555555555555",
    "workflow_state": "discussing"
  }'`,
        },
      ],
      relatedLink: '/docs/contracts#受保护写端点-post',
    },
    {
      id: 'post-api-topic-save',
      group: 'write',
      kind: 'POST',
      title: '追加讨论轮次 / 更正最近一轮',
      signature: 'POST /api/topic/{id}/save',
      auth: 'Host + Origin + CAS expected_version',
      stability: 'CAS + 幂等',
      summary:
        '基于 optimistic lock（expected_version）与 request_id 指纹原子更新三轴状态或追加一轮讨论；支持 edit_latest_round 原位修正刚刚提交的一轮。',
      capabilities: [
        '超时断开时可用原 request_id 与原 expected_version 原样重发，绝不重复追加轮次',
        '支持局部传参：省略字段维持原值，空字符串清空允许清空的字段',
      ],
      limitations: [
        '缺少 expected_version 强制返回 428 version_required',
        'edit_latest_round 只能修改最新一轮，禁止重写更早历史轮次',
      ],
      params: [
        { name: 'id', location: 'path', type: 'string', required: true, description: '目标议题 ID' },
        { name: 'expected_version', location: 'body', type: 'number', required: true, description: '读取到的最新版本号（亦可放 X-Expected-Version 头）' },
        { name: 'request_id', location: 'body', type: 'string', required: true, description: '本次写入幂等 UUID（亦可放 X-Request-Id 头）' },
        { name: 'new_user_opinion', location: 'body', type: 'string', description: '本轮确认的用户原话' },
        { name: 'new_agent_reply', location: 'body', type: 'string', description: '本轮 Agent 回应（可内嵌 agent-question）' },
        { name: 'edit_latest_round', location: 'body', type: 'boolean', defaultValue: 'false', description: '为 true 时仅修订最后一轮对应方内容' },
      ],
      responses: [
        {
          status: '200 OK',
          tone: 'ok',
          summary: '保存成功并写入 Markdown + SQLite 快照',
          example: `{
  "ok": true,
  "version": 4,
  "is_replay": false,
  "save_status": "saved",
  "git_status": "committed"
}`,
        },
        { status: '428 Precondition Required', tone: 'warn', summary: '缺少 expected_version（version_required）' },
        { status: '409 Conflict', tone: 'err', summary: 'version_conflict 或 idempotency_conflict（附带 current_version）' },
      ],
      examples: [
        {
          label: 'Python',
          code: `import json, uuid
from urllib.request import Request, urlopen

base = "{{BASE_URL}}"
topic = json.load(urlopen(f"{base}/api/topic/adr-storage"))
payload = {
    "expected_version": topic["version"],
    "request_id": str(uuid.uuid4()),
    "new_user_opinion": "同意保留 SQLite 快照表",
    "new_agent_reply": "已记录结论并准备核对边界。"
}
req = Request(f"{base}/api/topic/adr-storage/save", json.dumps(payload).encode(), {"Content-Type": "application/json"})
print(json.load(urlopen(req)))`,
        },
        {
          label: 'curl',
          code: `curl -X POST "{{BASE_URL}}/api/topic/adr-storage/save" \\
  -H "Content-Type: application/json" \\
  -d '{"expected_version":3,"request_id":"uuid-here","workflow_state":"decided","decision_outcome":"accepted"}'`,
        },
      ],
      relatedLink: '/docs/contracts#数据-三轴状态与幂等契约',
    },
    {
      id: 'post-api-topic-delete-restore',
      group: 'write',
      kind: 'POST',
      title: '单议题归档删除 / 快照恢复',
      signature: 'POST /api/topic/{id}/delete · /restore',
      auth: 'Host + Origin + CAS',
      stability: '可逆事务',
      summary:
        'delete 将 Markdown 移入 decisions/.archived_rollback/ 并记录 TOPIC_REMOVE 审计快照；restore 按 rev_id 将单议题回退或复原。',
      capabilities: [
        '删除不销毁历史，可经 TOPIC_REMOVE 的 prior_rev_id 无损还原',
        '复原已删除议题时自动赋予新单调版本号（ABA 防护）',
      ],
      limitations: [
        'delete 必须携带 expected_version；restore 对现存议题同样校验 expected_version',
        '不替代全库回滚（全库回滚使用 POST /api/rollback + expected_revision）',
      ],
      params: [
        { name: 'expected_version', location: 'body', type: 'number', required: true, description: '现存议题删除/恢复时必填' },
        { name: 'rev_id', location: 'body', type: 'string', description: '/restore 时目标快照 ID' },
        { name: 'request_id', location: 'body', type: 'string', required: true, description: '请求幂等 UUID' },
      ],
      responses: [
        {
          status: '200 OK',
          tone: 'ok',
          summary: '归档移动或指定版本恢复完成',
          example: `{ "ok": true, "rev_id": "rev-12", "save_status": "saved" }`,
        },
        { status: '409 Conflict', tone: 'err', summary: 'expected_version 过期冲突' },
      ],
      examples: [
        {
          label: 'curl (Restore)',
          code: `curl -X POST "{{BASE_URL}}/api/topic/adr-storage/restore" \\
  -H "Content-Type: application/json" \\
  -d '{"rev_id":"rev-2","author":"owner","reason":"恢复上一结论","request_id":"uuid-restore"}'`,
        },
      ],
      relatedLink: '/docs/architecture#持久化与恢复机制',
    },
    {
      id: 'post-api-topic-verify',
      group: 'write',
      kind: 'POST',
      title: '登记实现核验记录',
      signature: 'POST /api/topic/{id}/verify',
      auth: 'Host + Origin + CAS',
      stability: '台账登记',
      summary: '记录调用方提交的 impl_commit、verifier 与 test_summary 证据；服务端只登记台账结果。',
      capabilities: [
        '将已落实但尚未验收结论推进为 implemented 或 verified',
        '强制留存非空提交哈希与测试摘要供后续审计',
      ],
      limitations: [
        '语义非授权：服务端绝不替调用方执行 pytest / unittest 或验证 git commit 是否真的跑过测试',
      ],
      params: [
        { name: 'expected_version', location: 'body', type: 'number', required: true, description: 'CAS 版本号' },
        { name: 'impl_commit', location: 'body', type: 'string', required: true, description: '非空实现提交哈希或定位标记' },
        { name: 'verifier', location: 'body', type: 'string', required: true, description: '核验者标识' },
        { name: 'test_summary', location: 'body', type: 'string', required: true, description: '测试结果摘要' },
        { name: 'mark_verified', location: 'body', type: 'boolean', required: true, description: 'true 置 verified，false 保持 implemented' },
        { name: 'request_id', location: 'body', type: 'string', required: true, description: '幂等 UUID' },
      ],
      responses: [
        { status: '200 OK', tone: 'ok', summary: '实现核验状态已更新并入库' },
        { status: '400 Bad Request', tone: 'err', summary: 'impl_commit 为空或字段缺失' },
      ],
      examples: [
        {
          label: 'curl',
          code: `curl -X POST "{{BASE_URL}}/api/topic/adr-storage/verify" \\
  -H "Content-Type: application/json" \\
  -d '{"expected_version":4,"impl_commit":"abc1234","verifier":"cybernova","test_summary":"unittest passed","mark_verified":true,"request_id":"uuid-verify"}'`,
        },
      ],
      relatedLink: '/docs/contracts',
    },
    {
      id: 'post-api-backup-rollback',
      group: 'write',
      kind: 'POST',
      title: '热备份与全库快照回滚',
      signature: 'POST /api/backup · /api/rollback · /api/recovery/rebuild',
      auth: 'Host + Origin + expected_revision',
      stability: '运维事务',
      summary:
        '/api/backup 使用 SQLite Backup API 在同目录生成热备；/api/rollback 将整套台账退回全局 rev_id；/api/recovery/rebuild 锁内以 Markdown 重建索引。',
      capabilities: [
        '无需停服即可安全生成一致性 .bak_YYYYMMDD_HHMMSS SQLite 备份',
        '全局回滚强制校验 expected_revision，防并发覆盖他人的新提交',
      ],
      limitations: [
        '未知 expected_revision 调 /api/rollback 报 428；发现漂移阻断时 /api/recovery/rebuild 报 409',
        'metadata.json 无法作为重建来源（仅 decisions/*.md 是内容事实源）',
      ],
      params: [
        { name: 'rev_id', location: 'body', type: 'string', description: '/api/rollback 目标全局 revision ID' },
        { name: 'expected_revision', location: 'body', type: 'string', description: '/api/rollback 必填（取自 GET /api/git/log）' },
      ],
      responses: [
        {
          status: '200 OK',
          tone: 'ok',
          summary: '热备生成或重建/回滚成功',
          example: `{ "ok": true, "backup_path": "/path/to/decisions.db.bak_20261116_120000" }`,
        },
        { status: '428 Precondition Required', tone: 'warn', summary: '缺少 expected_revision' },
      ],
      examples: [
        {
          label: 'curl (Backup)',
          code: `curl -X POST "{{BASE_URL}}/api/backup" -H "Content-Type: application/json" -d '{}'`,
        },
      ],
      relatedLink: '/docs/contracts',
    },
    {
      id: 'cli-agent-hooks',
      group: 'agent',
      kind: 'CLI',
      title: '只读 Agent 钩子命令行',
      signature: 'python3 -m core.agent_hooks --config <cfg> before-task | after-write',
      auth: '本机回环 HTTP（禁用代理）',
      stability: '严格只读',
      summary:
        '供外部 AI Agent 工作流显式调用的只读命令行：before-task 校验目录路径与一致性并导出五桶上下文；after-write 核对保存回执是否真实生效。',
      capabilities: [
        '硬校验运行服务返回的绝对路径与 --config 配置目录一致，杜绝串库',
        '退出码 0/2 明确分流，错误 JSON 输出到 stderr 供 Agent 精确处理',
      ],
      limitations: [
        '严格只读：不自动创建、修改、删除议题，也不安装任何全局 Git hooks',
        'after-write 不适用于校验 delete_topic 归档或全库回滚',
      ],
      params: [
        { name: '--config', location: 'flag', type: 'path', required: true, description: '目标项目 dashboard.config.json' },
        { name: '--url', location: 'flag', type: 'url', description: '覆盖本机回环地址，仍强校目录一致性' },
        { name: '--module / --topic', location: 'flag', type: 'string', description: 'before-task 过滤模块或焦点议题' },
        { name: '--receipt', location: 'flag', type: 'path', description: 'after-write 必填的本地回执 JSON 文件路径' },
      ],
      responses: [
        {
          status: 'Exit 0',
          tone: 'ok',
          summary: '预检通过或回执核对一致，输出五桶 JSON 到 stdout',
          example: `{
  "ok": true,
  "project_name": "Demo",
  "active_decisions": [],
  "rejected_proposals": []
}`,
        },
        { status: 'Exit 2', tone: 'err', summary: '路径不一致、服务离线或一致性告警' },
      ],
      examples: [
        {
          label: 'CLI (before-task)',
          code: `python3 -m core.agent_hooks --config ./dashboard.config.json before-task --module 存储层`,
        },
        {
          label: 'CLI (after-write)',
          code: `python3 -m core.agent_hooks --config ./dashboard.config.json after-write --topic adr-storage --receipt ./receipt.json`,
        },
      ],
      relatedLink: '/docs/contracts#1-只读命令-core-agent_hooks',
    },
    {
      id: 'protocol-agent-question',
      group: 'agent',
      kind: 'SCHEMA',
      title: 'agent-question 单选交互围栏',
      signature: '```agent-question ... ``` (embedded in new_agent_reply)',
      auth: '单向 UI 协议',
      stability: '契约围栏',
      summary:
        '嵌入最新一轮 new_agent_reply 的轻量选项协议，在工作台前端渲染为可点击单选卡片（支持用户补充自由文本）。',
      capabilities: [
        '支持 1 个问题与 2-8 个带 label/description 的选项',
        '非法 JSON 或多块冲突自动退化为安全纯文本，绝不报错崩页',
      ],
      limitations: [
        '仅最新一轮有效，且界面刻意不设默认选中项',
        '选择结果仅记作用户原话，绝不自动篡改三轴状态或授予执行权',
      ],
      params: [
        { name: 'question', location: 'field', type: 'string', required: true, description: '待确认问题文本' },
        { name: 'options', location: 'field', type: '(string | {label, description})[]', required: true, description: '2 到 8 个互异选项' },
      ],
      responses: [
        {
          status: 'UI Card',
          tone: 'info',
          summary: '在最新一轮对话右下角渲染选项单选卡，提交时并入 new_user_opinion',
          example: `{
  "question": "这轮优先实现哪种方案？",
  "options": [
    { "label": "仅本机持久化", "description": "零外部依赖，先验证恢复流程" },
    { "label": "增加只读导出", "description": "附带生成结构化摘要" }
  ]
}`,
        },
      ],
      examples: [
        {
          label: 'Markdown Fence',
          code: `请确认本轮边界：

\`\`\`agent-question
{
  "question": "确认写入本轮存储选型吗？",
  "options": ["同意保留 SQLite", "推迟到下个里程碑"]
}
\`\`\``,
        },
      ],
      relatedLink: '/docs/contracts#3-agent-question-选项协议围栏',
    },
  ],
}

export const apiSpecEn: ApiCatalogSpec = {
  project: 'Agent Decisions Dashboard · API & Components',
  subtitle:
    'Complete loopback HTTP endpoints, CAS-guarded writes, recovery controls, and read-only agent CLI hooks. Loopback-only binding with a 10 MiB payload cap.',
  environments: [
    { label: 'Loopback Default', value: 'http://127.0.0.1:8765' },
    { label: 'Localhost Alias', value: 'http://localhost:8765' },
  ],
  searchPlaceholder: 'Filter endpoints, CLI commands, or schemas…',
  emptyText: 'No matching endpoint or component found.',
  labels: {
    allGroups: 'All',
    canDo: '✅ Capabilities',
    cannotDo: '⛔ Explicit Limits & Rejections',
    params: 'Parameters & Constraints',
    paramName: 'Field / Flag',
    paramLocation: 'In',
    paramType: 'Type',
    paramRequired: 'Required',
    paramDesc: 'Validation & Semantics',
    responses: 'Status & Exit Code Contracts',
    examples: 'Standard Invocation',
    responseSample: 'Response Payload',
    copy: 'Copy',
    copied: 'Copied',
    noParams: 'No additional parameters required.',
    required: 'Required',
    optional: 'Optional',
    deepDocs: 'Deep Contract Docs',
    totalItems: 'items',
    envLabel: 'Base URL',
    mobilePicker: 'Select Endpoint',
    defaultLabel: 'Default',
  },
  groups: [
    { id: 'query', title: 'Read-Only HTTP Queries' },
    { id: 'write', title: 'CAS Writes & Recovery' },
    { id: 'agent', title: 'Agent CLI & Protocol' },
  ],
  items: [
    {
      id: 'get-api-status',
      group: 'query',
      kind: 'GET',
      title: 'Server Status & Consistency Preflight',
      signature: 'GET /api/status',
      auth: 'Loopback only',
      stability: 'Read-Only',
      summary:
        'Returns active project metadata, canonical disk paths (decisions_dir, database_path, metadata_json_path), Git availability, and consistency summary.',
      capabilities: [
        'Confirms the live port points to the exact intended ledger directory',
        'Surfaces Markdown/SQLite drift before automated hooks proceed',
      ],
      limitations: [
        'Rejects non-loopback network hosts by design',
        'Never triggers repairs or filesystem mutations',
      ],
      responses: [
        {
          status: '200 OK',
          tone: 'ok',
          summary: 'Returns canonical paths and consistency report',
          example: `{
  "project_name": "Agent Decisions Dashboard",
  "decisions_dir": "/path/to/decisions",
  "database_path": "/path/to/decisions.db",
  "git_available": true,
  "consistency": { "ok": true, "mismatches": [] }
}`,
        },
      ],
      examples: [
        { label: 'curl', code: `curl -s {{BASE_URL}}/api/status` },
        {
          label: 'Python',
          code: `import json, urllib.request
with urllib.request.urlopen("{{BASE_URL}}/api/status") as r:
    print(json.load(r))`,
        },
      ],
      relatedLink: '/en/docs/contracts',
    },
    {
      id: 'get-api-topics',
      group: 'query',
      kind: 'GET',
      title: 'Filtered Topic Catalog',
      signature: 'GET /api/topics',
      auth: 'Loopback only',
      stability: 'Read-Only',
      summary:
        'Lists topics scoped by topic_scope.active_topic_ids together with orthogonal states, settled_decisions, and open_questions.',
      capabilities: [
        'Keeps list focused via active topic_scope configuration',
        'Exposes lifecycle definitions and category facets for UI rendering',
      ],
      limitations: [
        'Out-of-scope legacy topics are omitted here (fetch individually via GET /api/topic/{id})',
        'Omits full Markdown bodies and full discussion rounds',
      ],
      responses: [
        {
          status: '200 OK',
          tone: 'ok',
          summary: 'Returns scoped topic summaries and metadata',
          example: `{ "topics": [{ "id": "adr-storage", "version": 3, "workflow_state": "decided" }] }`,
        },
      ],
      examples: [
        { label: 'curl', code: `curl -s {{BASE_URL}}/api/topics` },
      ],
      relatedLink: '/en/docs/contracts',
    },
    {
      id: 'get-api-topic-detail',
      group: 'query',
      kind: 'GET',
      title: 'Single Topic Detail & Revisions',
      signature: 'GET /api/topic/{id}',
      auth: 'Loopback only',
      stability: 'Read-Only',
      summary:
        'Fetches full Markdown body, current CAS version, round-by-round discussion, and recent SQLite snapshots for any portable topic ID.',
      capabilities: [
        'Provides expected_version required for subsequent CAS saves',
        'Works directly even for topics excluded from topic_scope lists',
      ],
      limitations: [
        'Rejects non-portable IDs (path traversal, Windows reserved names)',
        'Returns 404 after delete archival (restore using TOPIC_REMOVE rev_id)',
      ],
      params: [
        { name: 'id', location: 'path', type: 'string', required: true, description: 'Portable topic identifier ([a-zA-Z0-9_-]{1,128})' },
      ],
      responses: [
        {
          status: '200 OK',
          tone: 'ok',
          summary: 'Returns full topic payload and current version',
          example: `{ "id": "adr-storage", "version": 3, "decision_outcome": "accepted", "discussion": [] }`,
        },
        { status: '404 Not Found', tone: 'err', summary: 'Topic absent or archived' },
      ],
      examples: [
        { label: 'curl', code: `curl -s {{BASE_URL}}/api/topic/adr-storage` },
      ],
      relatedLink: '/en/docs/contracts',
    },
    {
      id: 'get-api-agent-context',
      group: 'query',
      kind: 'GET',
      title: 'Five-Bucket Agent Context Export',
      signature: 'GET /api/agent/context',
      auth: 'Loopback only',
      stability: 'Read-Only',
      summary:
        'Exports active_decisions, rejected_proposals, pending_requirements, deferred_topics, and superseded_topics filtered by module, path, or topic_id.',
      capabilities: [
        'Routes partially_accepted into pending_requirements so boundaries remain visible',
        'Separates superseded rejections from active veto rules',
      ],
      limitations: [
        'Explicit unknown topic_id fails with 404 rather than silent empty success',
        'Informational ledger context only; never grants shell or test authority',
      ],
      params: [
        { name: 'module', location: 'query', type: 'string', description: 'Optional module category filter' },
        { name: 'topic_id', location: 'query', type: 'string', description: 'Optional single-topic focus' },
        { name: 'format', location: 'query', type: '"json" | "markdown"', defaultValue: 'json', description: 'Output format' },
      ],
      responses: [
        {
          status: '200 OK',
          tone: 'ok',
          summary: 'Returns 5-bucket structured context',
          example: `{ "active_decisions": [], "rejected_proposals": [], "pending_requirements": [], "deferred_topics": [], "superseded_topics": [] }`,
        },
        { status: '404 Not Found', tone: 'err', summary: 'Specified topic_id does not exist' },
      ],
      examples: [
        { label: 'curl', code: `curl -s "{{BASE_URL}}/api/agent/context?topic_id=adr-storage&format=json"` },
      ],
      relatedLink: '/en/docs/contracts',
    },
    {
      id: 'post-api-topic-save',
      group: 'write',
      kind: 'POST',
      title: 'Create or CAS-Save Topic Round',
      signature: 'POST /api/topic/create · POST /api/topic/{id}/save',
      auth: 'Host + Origin + Sec-Fetch-Site + CAS',
      stability: 'CAS + Idempotent',
      summary:
        'Atomically creates topics or appends/amends latest round in Markdown and SQLite under expected_version + request_id guarantees.',
      capabilities: [
        'Safe identical replay on timeout when reusing saved request_id + expected_version',
        'Decoupled response fields: save_status, export_status, git_status',
      ],
      limitations: [
        'Missing expected_version returns 428 version_required',
        'edit_latest_round restricts edits to the most recent round only; 10 MiB max body',
      ],
      params: [
        { name: 'expected_version', location: 'body', type: 'number', required: true, description: 'Optimistic lock version for /save' },
        { name: 'request_id', location: 'body', type: 'string', required: true, description: 'Idempotency UUID per write intent' },
        { name: 'new_user_opinion', location: 'body', type: 'string', description: 'Verified user statement' },
        { name: 'new_agent_reply', location: 'body', type: 'string', description: 'Agent response text (may contain agent-question)' },
      ],
      responses: [
        {
          status: '200 OK',
          tone: 'ok',
          summary: 'Saved or cleanly replayed (is_replay: true)',
          example: `{ "ok": true, "version": 4, "is_replay": false, "save_status": "saved", "git_status": "committed" }`,
        },
        { status: '428 Precondition Required', tone: 'warn', summary: 'Missing expected_version' },
        { status: '409 Conflict', tone: 'err', summary: 'version_conflict or idempotency_conflict' },
      ],
      examples: [
        {
          label: 'Python',
          code: `import json, uuid
from urllib.request import Request, urlopen

base = "{{BASE_URL}}"
t = json.load(urlopen(f"{base}/api/topic/adr-storage"))
body = {"expected_version": t["version"], "request_id": str(uuid.uuid4()), "new_user_opinion": "Confirmed"}
req = Request(f"{base}/api/topic/adr-storage/save", json.dumps(body).encode(), {"Content-Type": "application/json"})
print(json.load(urlopen(req)))`,
        },
      ],
      relatedLink: '/en/docs/contracts',
    },
    {
      id: 'post-api-ops-verify',
      group: 'write',
      kind: 'POST',
      title: 'Archive Delete, Verify, Backup & Rollback',
      signature: 'POST /api/topic/{id}/delete · /restore · /verify · /api/backup · /api/rollback',
      auth: 'Host + Origin + CAS / Revision',
      stability: 'Audit Ledger',
      summary:
        'Handles reversible archive deletion (.archived_rollback), snapshot restore, implementation commit verification logging, online SQLite hot backup, and full-ledger rollback.',
      capabilities: [
        'Online SQLite Backup API creates point-in-time .bak files without stopping server',
        'Tracks full audit snapshots for undeleting archived topics by rev_id',
      ],
      limitations: [
        '/verify records caller-supplied commit/test metadata only — it never executes tests',
        '/api/rollback rejects missing expected_revision with HTTP 428',
      ],
      params: [
        { name: 'expected_revision', location: 'body', type: 'string', description: 'Required for /api/rollback (from GET /api/git/log)' },
        { name: 'impl_commit', location: 'body', type: 'string', description: 'Required non-empty commit ref for /verify' },
      ],
      responses: [
        { status: '200 OK', tone: 'ok', summary: 'Operation completed and recorded' },
        { status: '428 Precondition Required', tone: 'warn', summary: 'Missing expected_version or expected_revision' },
      ],
      examples: [
        {
          label: 'curl (Backup)',
          code: `curl -X POST "{{BASE_URL}}/api/backup" -H "Content-Type: application/json" -d '{}'`,
        },
      ],
      relatedLink: '/en/docs/contracts',
    },
    {
      id: 'cli-agent-hooks',
      group: 'agent',
      kind: 'CLI',
      title: 'Read-Only Agent Hooks & Question Fence',
      signature: 'python3 -m core.agent_hooks before-task | after-write',
      auth: 'Loopback HTTP (no proxy)',
      stability: 'Strictly Read-Only',
      summary:
        'Explicit read-only CLI helpers verifying directory alignment before agent runs and confirming CAS writes afterward; paired with non-authorizing agent-question fences.',
      capabilities: [
        'Verifies server decisions_dir matches --config to prevent cross-project writes',
        'Exit codes 0 / 2 cleanly signal pass vs mismatch/offline error',
      ],
      limitations: [
        'Never installs global Git hooks or mutates ledger records automatically',
        'after-write is not for topic archival deletion or full-DB rollback',
      ],
      params: [
        { name: '--config', location: 'flag', type: 'path', required: true, description: 'Target dashboard.config.json' },
        { name: '--receipt', location: 'flag', type: 'path', description: 'Saved write receipt path for after-write' },
      ],
      responses: [
        { status: 'Exit 0', tone: 'ok', summary: 'Checks passed and context JSON emitted on stdout' },
        { status: 'Exit 2', tone: 'err', summary: 'Directory mismatch, offline server, or consistency failure' },
      ],
      examples: [
        {
          label: 'CLI',
          code: `python3 -m core.agent_hooks --config ./dashboard.config.json before-task --topic adr-storage`,
        },
      ],
      relatedLink: '/en/docs/contracts',
    },
  ],
}
