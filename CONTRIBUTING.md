# 贡献指南 / Contributing

## 贡献许可与附加条款约定 / Contribution Licensing & Additional Terms

依据 `LICENSE-ADDITIONAL_TERMS-zh-CN.md` 第 1.7 款，向本项目提交拉取请求（PR）、补丁或其他贡献时，即表示你确认对所提交内容享有合法授权权利，并同意你对第一方 AGPLv3 适用材料作出的贡献除适用 [GNU AGPLv3](LICENSE) 外，亦一并纳入 [`LICENSE-ADDITIONAL_TERMS-zh-CN.md`](LICENSE-ADDITIONAL_TERMS-zh-CN.md)（包括第 9.5–9.6 款有条件的扩展附加许可；英文参考译文见 [`LICENSE-ADDITIONAL_TERMS-en.md`](LICENSE-ADDITIONAL_TERMS-en.md)）适用范围；附带独立图标、美术或字体资产的，须按 [`ASSET_LICENSES.md`](ASSET_LICENSES.md) 如实提供来源与有效授权信息。既有上游或第三方多许可组件（如内核 GPLv2、上游 MIT / Apache-2.0 / GPL-2.0-or-later 代码）仍按仓库说明保留其各自原有许可。

By submitting a pull request, patch, or other contribution to this repository, you confirm that you hold the requisite rights to license your submission and agree pursuant to Section 1.7 of [`LICENSE-ADDITIONAL_TERMS-zh-CN.md`](LICENSE-ADDITIONAL_TERMS-zh-CN.md) (English reference: [`LICENSE-ADDITIONAL_TERMS-en.md`](LICENSE-ADDITIONAL_TERMS-en.md)) that your contributions to first-party Covered Material are licensed under GNU AGPLv3 (`LICENSE`) together with the Additional Terms (including the conditional additional permission in Sections 9.5–9.6, where applicable), and that any contributed standalone assets are documented under [`ASSET_LICENSES.md`](ASSET_LICENSES.md). Pre-existing upstream or third-party components retain their respective original licenses as documented in the repository.

<!-- repo-maintenance:begin -->
## 提交与核验 / Commits and verification

先阅读 [Agent 操作约束](AGENTS.md)、[项目指南](repo-docs/README.md) 和 [安全说明](SECURITY.md)。项目自己的兼容性、测试、署名与签名要求继续适用。

Use the project instructions, living guide and security policy before changing code. Existing compatibility, testing, attribution and signing requirements remain authoritative.

提交标题采用 `type(scope): 描述`，`scope` 可省略；允许 `feat`、`fix`、`docs`、`style`、`refactor`、`perf`、`test`、`build`、`ci`、`chore`、`revert`、`data`。标题不超过 100 个字符；仓库规定中文或更严格的类型集合时，遵守该仓库要求。正文解释原因、影响、实际验证结果和文档影响。一条提交对应一个可审阅的主题，签名和参与者尾注按真实身份填写。

Use Conventional Commits, with an optional scope and a subject of at most 100 characters. Follow stricter repository rules, including Chinese subjects where required. Explain the reason, effect, actual verification and documentation impact in the body. Attribute the real participants and retain the configured signing identity.

```sh
python tools/repo_maintenance_guard.py install
python tools/repo_maintenance_guard.py status
python tools/repo_maintenance_guard.py pre-commit
```

安装只修改当前克隆的 Git 配置。已有钩子会继续执行；新克隆需要重新安装。提交模板位于 `.gitmessage.txt`，已有自定义模板不会被覆盖。Git 钩子需要 Python 3.10+，不可完成检查时阻止本次操作并说明原因。项目自身的构建与测试命令见 README 和指南，安全扫描通过不代表业务测试通过。

Installation changes only this clone's Git configuration. Existing hooks continue to run. Install again in each fresh clone; an existing commit template is retained. Python 3.10+ is required. A failed security check stops the operation. Run the build and tests documented by this repository; passing the security scan does not establish application correctness.

历史信息整理仅用于维护者明确授权的场景。改写会改变提交编号；保持作者、提交者、日期、文件树与父图关系，保留原始引用和映射，并重新验证签名。发布改写后的历史需要独立核对远端引用与协作者状态。

Rewriting history requires an explicit maintenance request. Preserve identities, dates, trees, graph relationships and recovery references, then verify new signatures. Review remote state and collaborator impact separately before publishing rewritten history.
<!-- repo-maintenance:end -->
