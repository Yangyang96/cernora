# 参与 Cernora 开发

[English](CONTRIBUTING.md) | **简体中文**

感谢你参与改进 Cernora。所有贡献都应遵守项目的核心边界：对已经完成的 Agent
导出执行确定性、离线评测。

## 开始之前

- Evaluator 必须独立于 Agent 执行，不能启动进程、提供凭证、监督、创建沙箱或清理
  Agent。
- Agent Runtime 和 Experiment Harness 的实现应留在包外。Cernora 可以接收纯粹的
  completed-export Adapter，但不能接管执行或编排。
- 不要添加 Profile 注册中心、自动发现、市场、托管服务或 Runtime Provider 抽象。
- 不要在代码、fixture、文档或提交信息中放入密钥、私有证据、真实端点、个人路径、
  原始对话或客户数据。
- 如果改动会影响兼容性，请先在项目 Issue 中讨论。

修改公开契约前，请阅读[架构](docs/public/architecture.zh-CN.md)、
[兼容性矩阵](docs/public/compatibility-matrix.zh-CN.md)和
[证据发布策略](docs/public/evidence-publication-and-rebuild.zh-CN.md)。

## 开发环境

Cernora 支持 Python 3.12 和 3.13。安装 `uv` 并克隆仓库，然后创建锁定的开发环境：

```sh
uv sync --all-groups
```

开发时可运行针对性测试。提交前请从仓库根目录执行完整检查：

```sh
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run python -m build
git diff --check
```

准备发布候选时，使用统一命令运行上述检查、在全新临时目录中构建、验证 wheel 和源码归档，
再离线安装 wheel 并运行完整 Profile Authoring Loop：

```sh
uv run python scripts/release.py preflight
```

发布后，`uv run python scripts/release.py verify --version <version>` 会验证生产
PyPI 文件以及 Python 3.12/3.13 的干净安装流程。评审边界见
[本地发布检查清单](docs/public/local-release-checklist.zh-CN.md)。

## 改动要求

Pull Request 应当：

1. 说明用户可见行为和受影响的兼容性层级；
2. 按需提供成功、行为失败、格式错误或输入不兼容的确定性测试；
3. 保留对未知字段、版本、身份、摘要和权威的严格检查；
4. 将缺失、损坏或无法验证的证据归类为 `inconclusive`，不能判为 `pass`；
5. fixture 应小型、中立、可复现，且不含凭证或机器相关数据；
6. Preview 或 Supported Preview 发生变化时，更新 `CHANGELOG.md` 和迁移说明。

不要为了让测试通过而削弱 fixture、预期观察、分数、阈值或 Gate。应修复实现；如果
契约确实需要变化，请说明原因并提交经过评审的版本化改动。

## 兼容性策略

Supported Preview 接口在整个 `0.1.x` 期间保持兼容。破坏这些接口需要发布 `0.2.0`
并提供迁移说明。Profile 和 Adapter 编写 API 属于 Preview，可以在 `0.1.x` 内演进；
破坏性改动需要 changelog、迁移说明，并应在可行时先弃用。Internal 模块不提供兼容承诺。

EvidenceBundle v2 和 import v2 是 `0.1.x` 唯一的公开输入格式。Evidence、Score 和
GateDecision 保留 v1 wire ID；不要重新标记或解释既有字节。

## 文档与来源

只使用相对链接、可运行命令和公开名称。生成的证据必须能通过文档中的确定性命令重建。
摘要可以证明内容完整性，但不能证明内容由谁产生、Producer 未受攻击或历史不可变。

贡献内容按 `LICENSE` 中的 Apache License 2.0 接收。
