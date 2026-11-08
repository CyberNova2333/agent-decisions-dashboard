---
version: 2.0.0
name: Agent Decisions Dashboard Primer Tactile Design System
description: 面向多智能体架构决策台账与 Git 治理看板（agent-decisions-dashboard）的 Primer 质感设计系统规范。将 GitHub Primer 功能原语与工程座舱物理质感深度融合，强制执行 14px 高密度排版、Light/Dark 四级画布分层、8px 空间网格、物理斜角高光 Box 容器、微拟物触觉按压反馈、四维决策状态微拟物胶囊以及 WCAG AA 无障碍标准。
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

# Agent Decisions Dashboard 质感设计系统规范 (`DESIGN.md`)

本文档是 [`agent-decisions-dashboard`](file:///D:/Projects/CyberNova2333/git-repos/agent-decisions-dashboard) 的质感设计系统规范。项目基于 GitHub Primer 功能主义设计体系，引入**工程座舱与决策台账质感设计（Engineering Cockpit & Ledger Tactile Materiality）**，针对多智能体协作、四维状态治理、多轮问答讨论流、CAS 乐观锁冲突解决与全屏专注审阅工作流，实现微拟物光影分层、物理斜角高光与触觉按压反馈。

---

## 1. 核心设计哲学与物理质感

### 1.1 质感工程座舱美学（Engineering Cockpit Materiality）
1. **Productive Complexity（高产出的复杂性）**：决策台账承载“生命周期（Workflow）”、“决策结论（Outcome）”、“实现进度（Implementation）”与“架构分域（Object）”四维元数据。通过 `14px` 高密度正文锚点、`32px` 控件物理基准高度与 Primer `Box` 容器容纳高信息密度。
2. **定向顶光与斜角高光（Chamfered Bevel Key Light）**：所有卡片容器、按钮与状态徽章均拥有顶边缘物理斜角微高光（`inset 0 1px 0 rgba(255, 255, 255, 0.25)`），模拟工业仪器面板由顶部环境光照射产生的金属边角微反光。
3. **物理触觉按压（Tactile Kinematics）**：交互按钮与可点击选项行具备物理按压反馈（`:hover` 上浮 `translateY(-0.5px)`，`:active` 下陷 `translateY(0.5px) scale(0.99)` + `inset 0 2px 4px rgba(0, 0, 0, 0.3)`），使决策确认具备实体机械开关的明确触感。
4. **四维微拟物状态胶囊（Tactile Status Pills）**：采用 `9999px` 纯圆角，表面具备微拟物斜角高光与语义描边（`1px solid`），不仅靠颜色区分状态，更具立体徽章的实体压印感。

---

## 2. 调色板与语义 Token

### 2.1 W3C `$value/$type` Token 注册表

| Primer 功能 Token | YAML 键名 | Light `$value` | Dark `$value` | 物理质感与组件绑定 |
| :--- | :--- | :--- | :--- | :--- |
| `accent.fg` | `accent-fg` / `accent-dark-fg` | `#0969da` | `#2f81f7` | 议题链接、当前选中项、2px 物理焦点环 |
| `accent.emphasis` | `accent-emphasis` | `#0969da` | `#1f6feb` | Primary 主按钮填充、新建议题实体按钮 |
| `accent.subtle` | `accent-subtle` | `#ddf4ff` | `rgba(56,139,253,0.15)` | 架构分域胶囊底色、Agent 协议卡微光底色 |
| `canvas.default` | `canvas-default` / `canvas-dark-default` | `#ffffff` | `#0d1117` | 页面主工作区背景、议题 `Box` 卡片主体底色 |
| `canvas.overlay` | `canvas-overlay` / `canvas-dark-overlay` | `#ffffff` | `#161b22` | 议题详情弹窗（Modal）、侧滑历史抽屉（Drawer）底色 |
| `canvas.inset` | `canvas-inset` / `canvas-dark-inset` | `#f6f8fa` | `#010409` | 顶部全局导航栏、左侧筛选边栏、代码块内凹底色 |
| `canvas.subtle` | `canvas-subtle` / `canvas-dark-subtle` | `#f6f8fa` | `#161b22` | `Box-header` 栏、列表行悬停背景、次要按钮底色 |
| `fg.default` | `fg-default` / `fg-dark-default` | `#1f2328` | `#f0f6fc` | 议题主标题、双方讨论正文、表单输入文字 |
| `fg.muted` | `fg-muted` / `fg-dark-muted` | `#57606a` | `#8b949e` | 议题 ID、版本号、时间戳、摘要预览 |
| `border.default` | `border-default` / `border-dark-default` | `#d0d7de` | `#30363d` | 容器物理边框（1px solid）、输入框边框 |
| `success.fg` | `success-fg` / `success-dark-fg` | `#1a7f37` | `#3fb950` | `已决策`、`已采纳`、`已实现` 状态胶囊 |
| `attention.fg` | `attention-fg` / `attention-dark-fg` | `#9a6700` | `#d29922` | `讨论中`、`部分同意` 状态胶囊 |
| `danger.fg` | `danger-fg` / `danger-dark-fg` | `#cf222e` | `#f85149` | `已否决`、CAS 版本冲突警告面板 |
| `done.fg` | `done-fg` / `done-dark-fg` | `#8250df` | `#a371f7` | `已核验`、`已替代` 状态胶囊 |

---

## 3. 字体栈与空间规范

- **无衬线字体栈（`--font-sans`）**：`-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans', Helvetica, Arial, sans-serif`
- **等宽字体栈（`--font-mono`）**：`ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, 'Liberation Mono', 'IBM Plex Mono', monospace`
- **基准字阶**：全局正文 `14px`（行高 `1.5`），卡片标题 `16px`（字重 `600`），大弹窗标题 `20px`（字重 `600`），状态胶囊 `12px`。
- **8px 空间网格**：全站间距严格对齐 `4px / 8px / 12px / 16px / 24px / 32px`。

---

## 4. 核心组件交互与物理表现

### 4.1 Topic Box Card（议题卡片：`.topic-card`）
- **静止态**：标准 Primer `Box` 造型，深色模式具备物理外框与内边缘高光 `box-shadow: 0 1px 3px rgba(1, 4, 9, 0.4), inset 0 1px 0 rgba(255, 255, 255, 0.05)`。
- **悬停态**：边框加亮为 `accent.fg`（`#0969da` / `#2f81f7`），顶边缘微光增强，下投影拓展为 `0 6px 18px rgba(1, 4, 9, 0.35)`。
- **点击态**：触发平滑卡片展开，进入审阅专注视图。

### 4.2 实体操作按钮（Tactile Buttons）
- **次要按钮（`.btn`）**：顶边缘带 `inset 0 1px 0 rgba(255, 255, 255, 0.25)` 斜角反光，`:hover` 上浮 `0.5px`，`:active` 下陷 `0.5px` 并伴随内嵌阴影 `inset 0 2px 4px rgba(0, 0, 0, 0.3)`。
- **主要按钮（`.btn.primary`）**：实心品牌蓝渐变填充，高对比白色文字，具备更深的实体下按深度。

### 4.3 CAS 并发冲突横幅（`.conflict-banner`）
- 发生 `409 VersionConflictError` 时展开，左侧具备 `3px solid var(--danger-fg)` 物理警示立柱，左右并列展示“远端提交版本”与“本地草稿”，Diff 增删行采用红绿双色微拟物底色。
