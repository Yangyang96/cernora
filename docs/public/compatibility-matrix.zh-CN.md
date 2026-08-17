# 兼容性矩阵

[English](compatibility-matrix.md) | **简体中文**

Cernora `0.1.x` 尚未达到 1.0。兼容性按层级定义，不把所有可导入模块都视为稳定接口。

|接口面|层级|`0.1.x` 策略|
|---|---|---|
|Python 3.12 和 3.13|Supported Preview|已测试的发布范围；移除任一版本都需要 minor 版本和迁移说明。|
|`cernora evidence import` 和 `cernora evidence evaluate`|Supported Preview|命令形态、退出类别和 canonical JSON 行为保持兼容。|
|`cernora profile init` 和 `cernora profile validate`|Supported Preview|默认私有 workspace 和显式 Profile 选择保持兼容。|
|EvidenceBundle v2 和 import receipt/manifest v2|Supported Preview|`0.1.x` 内不重新解释 wire 字段和严格验证语义。|
|Evidence v1、Score v1、GateDecision v1|Supported Preview|保留既有 wire ID 和 canonical 语义。|
|文档化的 package-root model 与 import/evaluate 函数|Supported Preview|`0.1.x` 内兼容；可以在不改变既有行为的前提下新增接口。|
|Canonicalization、权威绑定、摘要检查、冲突安全发布、严格 reload 和 fail-closed|Supported Preview|保留安全语义，不会为了兼容而放宽。|
|`Profile`、`Adapter`、编写 dataclass 和 conformance helper|Preview|可以在 `0.1.x` 内随 changelog 和迁移说明演进；可行时先弃用。|
|Reference Profile 布局和 Profile 特定 helper|Preview|可以按迁移文档演进；Profile 权威版本始终显式。|
|未从 `cernora` 重新导出的模块、parser/storage 实现、测试和构建脚本|Internal|不作兼容承诺。|

## 平台支持矩阵

`py3-none-any` wheel tag 只描述打包，不是操作系统支持证据。下表记录 `0.1.0` 在
2026-08-14 的发布声明。

|平台|Python / 架构 / 安装方式|状态|原生证据|排除项与发布条件|
|---|---|---|---|---|
|macOS|CPython 3.12/3.13；Apple silicon (`arm64`)；wheel 和 sdist 构建 wheel|Supported Preview|macOS 26.4 `arm64` 原生验收在源码目录外使用 Python 3.12/3.13 安装最终 wheel；Darwin 原子 no-replace 分支和打包示例通过。外部发布证据绑定精确 artifact 摘要。|Intel Mac 和旧版 macOS 尚未测试。|
|Linux|CPython 3.12/3.13；Ubuntu GitHub-hosted runner；wheel 和 sdist 构建 wheel|Not yet supported|GitHub CI 对发布 commit 执行源码检查和精确 wheel 验收，但尚未作为独立 Linux 支持资格接受。|原子发布竞争条件和完整 README 流程形成平台支持证据包前，不声明 Linux 支持。其他发行版和架构未测试。|
|Windows|CPython 3.12/3.13；架构尚未认定；wheel 和 sdist 构建 wheel|Not yet supported|Windows 原子目录发布分支只有代码评审，没有原生运行或 Windows CI。|更改状态前需增加原生 Windows CI，覆盖原子发布竞争条件和 README 流程。|

平台支持范围刻意窄于 Python 语言兼容范围。后续原生运行可以提升某个平台状态而不改变
wire contract，但必须先记录证据日期、解释器、架构和精确 artifact 摘要。

## 版本化输入与输出

公开输入只有 EvidenceBundle v2 和 canonical import v2。Cernora `0.1.x` 不接受、
转换、分发或静默升级 bundle/import v1。

公开链路保留：

```text
agent.evaluator.evidence-bundle/v2
agent.evaluator.evidence/v1
agent.evaluator.score/v1
agent.evaluator.gate-decision/v1
```

版本号不同是有意设计。Bundle v2 是支持评测的输入；既有 Evidence、Score 和
GateDecision 输出契约保留 v1。Wire ID 是协议身份，不跟随 Python 包名变化。

## 变更规则

- 破坏 Supported Preview 接口需要发布 `0.2.0` 并提供迁移说明。
- `0.1.x` 内的 Preview 破坏性改动需要 changelog 和迁移说明，可行时提供弃用期。
- 增强验证可以拒绝从未满足公开契约的内容，但不能重新解释过去有效的 canonical 字节。
- 权威变化必须按需显式更新 Profile、Case、fixture、Scorer 或 Gate 版本。
- 不能为了保持行为而接受损坏、不完整或权威不兼容的输入。

## 退出类别

|退出码|含义|
|---|---|
|`0`|命令成功，或 eligible evaluation 通过。|
|`1`|Eligible evidence 证明行为失败。|
|`2`|用法、选择或权威配置不兼容。|
|`3`|证据损坏、不完整、不可判定，或其他 fail-closed 错误。|

## 明确排除

兼容承诺不包含 Agent Runtime、执行 sandbox、托管服务、Profile 注册中心、自动发现、
市场、数据库、Experiment Harness、runtime receipt 捕获或部署权威。`0.1.x` 中不存在这些
接口。
