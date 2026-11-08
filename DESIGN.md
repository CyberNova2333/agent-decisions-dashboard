---
version: 1.0.0
name: Agent Decisions Dashboard Primer Design System
description: 面向多智能体架构决策台账与 Git 治理看板（agent-decisions-dashboard）的 Primer 设计系统规范。与 CloudForge 同色系同风格，基于 GitHub Primer 功能原语强制执行 14px 高密度排版、Light/Dark 四级画布分层（#ffffff/#f6f8fa 与 #0d1117/#161b22/#010409）、8px 空间网格、6px 圆角 1px 边框 Box 容器、四维决策状态胶囊以及 WCAG AA 无障碍标准。
colors:
  primary: '#0969da'
  accent-fg: '#0969da'
  accent-emphasis: '#0969da'
  accent-subtle: '#ddf4ff'
  accent-dark-fg: '#2f81f7'
  canvas-default: '#ffffff'
  canvas-overlay: '#ffffff'
  canvas-inset: '#f6f8fa'
  canvas-subtle: '#f6f8fa'
  canvas-dark-default: '#0d1117'
  canvas-dark-overlay: '#161b22'
  canvas-dark-inset: '#010409'
  canvas-dark-subtle: '#161b22'
  fg-default: '#1f2328'
  fg-muted: '#57606a'
  fg-on-emphasis: '#ffffff'
  fg-dark-default: '#f0f6fc'
  fg-dark-muted: '#8b949e'
  border-default: '#d0d7de'
  border-muted: '#d8dee4'
  border-subtle: '#e1e4e8'
  border-dark-default: '#30363d'
  border-dark-muted: '#21262d'
  success-fg: '#1a7f37'
  success-emphasis: '#1f883d'
  success-subtle: '#dafbe1'
  success-dark-fg: '#3fb950'
  danger-fg: '#cf222e'
  danger-emphasis: '#cf222e'
  danger-subtle: '#ffebe9'
  danger-dark-fg: '#f85149'
  attention-fg: '#9a6700'
  attention-subtle: '#fff8c5'
  attention-dark-fg: '#d29922'
  done-fg: '#8250df'
  done-subtle: '#fbefff'
  done-dark-fg: '#a371f7'
  underline-active: '#fd8c73'
typography:
  body-md:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans', Helvetica, Arial, sans-serif"
    fontSize: 14px
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: 0px
  body-sm:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans', Helvetica, Arial, sans-serif"
    fontSize: 12px
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: 0px
  ui-label:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans', Helvetica, Arial, sans-serif"
    fontSize: 14px
    fontWeight: 600
    lineHeight: 1.4285
    letterSpacing: 0px
  heading-page:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans', Helvetica, Arial, sans-serif"
    fontSize: 20px
    fontWeight: 600
    lineHeight: 1.4
    letterSpacing: -0.2px
  heading-section:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans', Helvetica, Arial, sans-serif"
    fontSize: 16px
    fontWeight: 600
    lineHeight: 1.5
    letterSpacing: 0px
  code-inline:
    fontFamily: "ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, 'Liberation Mono', 'IBM Plex Mono', monospace"
    fontSize: 12px
    fontWeight: 500
    lineHeight: 1.5
    letterSpacing: 0px
rounded:
  none: 0px
  sm: 3px
  md: 6px
  lg: 12px
  pill: 9999px
spacing:
  none: 0px
  xxs: 4px
  xs: 8px
  sm: 12px
  md: 16px
  lg: 24px
  xl: 32px
components:
  dashboard-header:
    backgroundColor: '{colors.canvas-inset}'
    textColor: '{colors.fg-default}'
    typography: '{typography.heading-page}'
    rounded: '{rounded.none}'
    padding: '{spacing.md}'
  topic-box:
    backgroundColor: '{colors.canvas-default}'
    textColor: '{colors.fg-default}'
    typography: '{typography.body-md}'
    rounded: '{rounded.md}'
    padding: '{spacing.md}'
  topic-box-header:
    backgroundColor: '{colors.canvas-subtle}'
    textColor: '{colors.fg-muted}'
    typography: '{typography.body-sm}'
    rounded: '{rounded.md}'
    padding: '{spacing.sm}'
  badge-accepted:
    backgroundColor: '{colors.success-subtle}'
    textColor: '{colors.success-fg}'
    typography: '{typography.body-sm}'
    rounded: '{rounded.pill}'
    padding: '{spacing.xxs}'
  badge-discussing:
    backgroundColor: '{colors.attention-subtle}'
    textColor: '{colors.attention-fg}'
    typography: '{typography.body-sm}'
    rounded: '{rounded.pill}'
    padding: '{spacing.xxs}'
  badge-rejected:
    backgroundColor: '{colors.danger-subtle}'
    textColor: '{colors.danger-fg}'
    typography: '{typography.body-sm}'
    rounded: '{rounded.pill}'
    padding: '{spacing.xxs}'
  badge-verified:
    backgroundColor: '{colors.done-subtle}'
    textColor: '{colors.done-fg}'
    typography: '{typography.body-sm}'
    rounded: '{rounded.pill}'
    padding: '{spacing.xxs}'
---

# Agent Decisions Dashboard Primer 设计系统规范 (`DESIGN.md`)

本文档是 [`agent-decisions-dashboard`](file:///D:/Projects/CyberNova2333/git-repos/agent-decisions-dashboard) 的设计系统规范，与同系列标杆项目 [`cloudforge/DESIGN.md`](file:///D:/Projects/CyberNova2333/git-repos/cloudforge/DESIGN.md) 保持**同色系同风格（GitHub Primer Functional Design System）**，并针对架构决策台账的四维状态治理、多轮问答讨论流、CAS 乐观锁冲突解决、Git 快照回滚以及全屏专注审阅工作流进行专项适配。

---

## Overview

本项目遵循 GitHub Primer 的四条核心工程设计哲学：

1. **Productive Complexity（高产出的复杂性）**：决策议题同时携带“生命周期（Workflow）”、“决策结论（Outcome）”、“实现进度（Implementation）”与“架构分域（Object）”四维元数据以及多轮双方原话。通过克制的 `14px` 正文锚点、`32px` 控件高度、Primer `Box` 分层容器（`1px solid` 边框 + `6px` 圆角）与清晰的 `UnderlineNav` 视图标签页承载高密度信息，拒绝浮夸留白与廉价的无边框色块。
2. **Accessibility-First（无障碍优先）**：Light 与 Dark 模式下正文对比度均大于 `4.5:1`，四维状态胶囊同时具备柔和语义底色、高对比文字与 `1px solid` 语义描边（绝不仅靠颜色区分状态），所有交互控件具备 `2px solid` 蓝色焦点环（`#0969da` / `#2f81f7`）。
3. **Pragmatic Visuals（务实视觉）**：坚持零渐变按钮、零毛玻璃浮层、零卡片悬停位移缩放。深度仅由四级画布（`canvas.inset` → `canvas.default` → `canvas.subtle` → `canvas.overlay`）与 `1px solid` 边框灰阶表达。
4. **Consistency through Primitives（原语驱动的一致性）**：全局 CSS 变量严格对齐 Primer 功能原语（`--canvas-*`、`--fg-*`、`--border-*`、`--accent-*`、`--success-*`、`--attention-*`、`--danger-*`、`--done-*`）。

---

## Colors

### W3C `$value/$type` Token 注册表

| Primer 功能 Token | YAML 键名 | W3C `$type` | Light `$value` | Dark `$value` | 用途与组件绑定 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `accent.fg` | `accent-fg` / `accent-dark-fg` | `color` | `#0969da` | `#2f81f7` | 议题链接、当前选中项、进行中状态、2px 焦点环 |
| `accent.emphasis` | `accent-emphasis` | `color` | `#0969da` | `#1f6feb` | Primary 主按钮填充、新建议题按钮、保存按钮背景 |
| `accent.subtle` | `accent-subtle` | `color` | `#ddf4ff` | `rgba(56,139,253,0.15)` | 架构分域胶囊底色、进行中状态底色、Agent 问题协议卡高亮 |
| `canvas.default` | `canvas-default` / `canvas-dark-default` | `color` | `#ffffff` | `#0d1117` | 页面主工作区背景、议题 `Box` 卡片主体底色、模态窗主体底色 |
| `canvas.overlay` | `canvas-overlay` / `canvas-dark-overlay` | `color` | `#ffffff` | `#161b22` | 议题详情模态弹窗（Modal）、侧滑历史抽屉（Drawer）浮层底色 |
| `canvas.inset` | `canvas-inset` / `canvas-dark-inset` | `color` | `#f6f8fa` | `#010409` | 顶部全局导航栏（Header）、左侧筛选边栏（Sidebar）、代码块内凹底色 |
| `canvas.subtle` | `canvas-subtle` / `canvas-dark-subtle` | `color` | `#f6f8fa` | `#161b22` | `Box-header` 栏、表头、列表行悬停背景、Default 次要按钮底色 |
| `fg.default` | `fg-default` / `fg-dark-default` | `color` | `#1f2328` | `#f0f6fc` | 议题主标题、双方讨论正文、表单输入文字 |
| `fg.muted` | `fg-muted` / `fg-dark-muted` | `color` | `#57606a` | `#8b949e` | 议题 ID、版本号（`v1`）、时间戳、摘要预览、筛选分组眉标 |
| `fg.onEmphasis` | `fg-on-emphasis` | `color` | `#ffffff` | `#ffffff` | Primary / Danger 实心按钮上的高对比白色文字 |
| `border.default` | `border-default` / `border-dark-default` | `color` | `#d0d7de` | `#30363d` | `Box` 卡片外框、输入框边框、按钮边框、顶栏与侧栏分隔线 |
| `border.muted` | `border-muted` / `border-dark-muted` | `color` | `#d8dee4` | `#21262d` | 讨论轮次时间线分隔、概览表行间分隔线 |
| `success.fg` | `success-fg` / `success-dark-fg` | `color` | `#1a7f37` | `#3fb950` | `已决策 (decided)`、`已采纳 (accepted)`、`已实现 (implemented)` 文字与图标 |
| `success.subtle` | `success-subtle` | `color` | `#dafbe1` | `rgba(46,160,67,0.15)` | 采纳/已决策胶囊底色、成功提示条底色 |
| `attention.fg` | `attention-fg` / `attention-dark-fg` | `color` | `#9a6700` | `#d29922` | `讨论中 (discussing)`、`部分同意 (partially_accepted)` 文字与图标 |
| `attention.subtle` | `attention-subtle` | `color` | `#fff8c5` | `rgba(187,128,9,0.15)` | 讨论中/部分同意胶囊底色、未保存草稿提醒横幅底色 |
| `danger.fg` | `danger-fg` / `danger-dark-fg` | `color` | `#cf222e` | `#f85149` | `已否决 (rejected)`、CAS 版本冲突警告、回滚破坏性操作文字 |
| `danger.subtle` | `danger-subtle` | `color` | `#ffebe9` | `rgba(248,81,73,0.15)` | 否决结论胶囊底色、CAS 冲突对比横幅（`.conflict-banner`）底色 |
| `done.fg` | `done-fg` / `done-dark-fg` | `color` | `#8250df` | `#a371f7` | `已核验 (verified)`、`已替代 (superseded)` 状态文字与图标 |
| `done.subtle` | `done-subtle` | `color` | `#fbefff` | `rgba(163,113,247,0.15)` | 已核验（Verified）与已替代胶囊底色 |

---

## Typography

### 字体栈与字阶规范

- **无衬线字体栈（`--font-sans`）**：`-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans', Helvetica, Arial, sans-serif, 'Apple Color Emoji', 'Segoe UI Emoji'`
- **等宽字体栈（`--font-mono`）**：`ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, 'Liberation Mono', 'IBM Plex Mono', monospace`

| 字阶角色 | 字号 | 字重 | 行高 | 适用场景 |
| :--- | :--- | :--- | :--- | :--- |
| `heading-page` | `20px` | `600` | `1.4` | 议题详情弹窗标题、全屏审阅模式主标题 |
| `heading-section` | `16px` | `600` | `1.5` | 顶栏应用名、议题卡片标题（`.topic-title`）、区块头部标题 |
| `body-md` | **`14px`** | `400` | `1.5` | **全局 `body` 强制基准字号**。用于议题摘要、多轮讨论正文、表单输入与概览表格 |
| `ui-label` | `14px` | `600` | `1.4285` | 按钮标签、UnderlineNav 视图切换项、表单字段 Label |
| `body-sm` | `12px` | `400`–`600` | `1.5` | 四维状态胶囊（`.badge`）、侧边栏分组眉标、轮次时间戳 |
| `code-inline` | `12px` | `500` | `1.5` | 议题 ID（`topic-id`）、Git Commit SHA 短码、Revision 哈希与代码块 |

---

## Layout & Spacing

1. **8px 空间网格**：全站间距严格取自 `4px / 8px / 12px / 16px / 24px / 32px`。
2. **Primer Shell 架构**：
   - **顶部导航栏（`.app-header`）**：高度 `56px`，背景 `canvas.inset`（`#f6f8fa` Light / `#010409` Dark），底边 `1px solid border.default`。左侧展示应用标识与在线状态胶囊，右侧排列操作按钮组（高度 `32px`，圆角 `6px`）。
   - **左侧筛选边栏（`.sidebar`）**：宽度 `260px`，背景 `canvas.inset`，右边 `1px solid border.default`。包含搜索框、4 项统计概览小卡（`.stat-card`）以及按维度分组的筛选按钮（激活项左侧附 `3px` 实心 `#0969da` / `#2f81f7` 指示条，背景 `canvas.muted`）。
   - **主工作区（`.main-content`）**：背景 `canvas.default`（`#ffffff` / `#0d1117`），顶部为 Primer `UnderlineNav` 风格视图栏（当前激活视图底部带 `2px solid #fd8c73` 指示线）。

---

## Components

### 1. Topic Box Card（议题卡片：`.topic-card`）
- **交互状态**：
  - `default`：标准 Primer `Box`（背景 `canvas.default`，边框 `1px solid border.default`，圆角 `6px`，静止态阴影 `0 1px 0 rgba(27,31,35,0.04)`）。顶部元数据行展示等宽议题 ID、版本号与四维状态胶囊（`border-radius: 9999px`）；中部为 `16px` 加粗标题与 2 行截断摘要；底部为 `canvas.subtle` 信息栏（显示轮次数与最近更新时间）。
  - `hover`：边框色切换为 `accent.fg`（`#0969da` / `#2f81f7`），标题文字变为 `accent.fg`，**严禁发生 `translateY` 位移或 `scale` 缩放**。
  - `focus`：`2px solid var(--focus-outline)` 焦点环。
  - `active`：点击打开议题详情审阅弹窗。
  - `disabled`：已归档或已替代议题降低不透明度至 `0.75`。

### 2. Discussion Timeline & Agent Question Box（讨论时间线与结构化问题卡：`.round-item` / `.agent-question-box`）
- **交互状态**：
  - `default`：效仿 GitHub Issue/PR Timeline，左侧贯穿 `2px` 宽 `border.muted` 时间轴，每轮讨论封装在 `1px solid border.default` + `6px` 圆角的 `Box` 中，`Box-header` 使用 `canvas.subtle` 背景标明发言角色（User / Agent）与轮次号。当 Agent 回复包含 `agent-question` 协议块时，渲染为 `accent.subtle` 头部 + 单选选项行（`.agent-question-option`）的交互式决策卡。
  - `hover`：问题选项行悬停背景切换为 `canvas.subtle`，边框加深为 `border.default`。
  - `focus`：`2px solid var(--focus-outline)`。
  - `active`：选中选项行高亮为 `accent.subtle` 背景与 `1px solid accent.fg` 边框，自动回填用户意见输入框。

### 3. CAS Conflict Banner & Full-Screen Review Mode（并发冲突横幅与全屏审阅模式：`.conflict-banner` / `.review-sheet`）
- **交互状态**：
  - `default`：当发生 `409 VersionConflictError` 时，在弹窗顶部渲染 `danger.subtle` 背景 + `1px solid danger.muted` + 左侧 `3px solid danger.fg` 的冲突对比面板，并列展示“服务器最新版本”与“本地未保存草稿”。全屏审阅模式（`.review-sheet`）将议题纵向铺满 `1280px` 居中工作台，支持逐条翻页审阅。

---

## Focus & Motion

- **键盘焦点**：全局 `:focus-visible` 统一采用 `outline: 2px solid var(--focus-outline); outline-offset: 2px`（在实心主按钮外保留 `2px` 间隙）。
- **动效规范**：悬停与状态切换控制在 `120ms ease-out`，严禁弹跳曲线；完整支持 `@media (prefers-reduced-motion: reduce)`。

---

## Do's and Don'ts

- ✅ **Do**：所有容器严格使用 `1px solid var(--border-default)` 与 `6px` 圆角，状态胶囊使用 `9999px` 胶囊圆角与语义描边。
- ❌ **Don't**：严禁使用渐变按钮、毛玻璃背景或无边框灰色色块，严禁把正文字号放大到 `16px`。
