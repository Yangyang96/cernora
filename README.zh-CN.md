# Cernora

[English](README.md) | **简体中文**

> 面向工具型 Agent 的证据绑定评测。

Cernora 是一个面向已完成 Agent Run 的独立评测内核。它离线且运行时中立，
把 Producer 拥有的完成态导出转换成由 Evaluator 独立生成、可复现的结果：

```text
completed export -> EvidenceBundle v2 -> Import -> Evidence -> Score -> GateDecision
```

Cernora 不询问 Runtime“是否成功”，而是验证其导出的证据，将证据与明确
版本的 Profile 和 Case 绑定，严格重新加载每一个持久化结果；当证据或评测
权威缺失、不一致或损坏时，系统会 fail closed。

> **当前版本：** `0.1.0` 是首个正式公开版本。Python 3.12 和 3.13 是已测试的
> 语言版本；操作系统状态见
> [平台矩阵](docs/public/compatibility-matrix.md#platform-support-matrix)。

## 为什么需要 Cernora？

看起来正确的最终回答，并不能证明 Agent 正确完成了任务。

Agent 可能选择了错误工具、传入错误参数、忽略工具返回、修改意外的产物，
也可能在执行环境失败后仍然报告成功。如果这些情况最终都被压缩成一个分数，
Agent 行为失败和评测本身无效就无法区分。

Cernora 明确区分三件事：

- **执行权和评测权相互独立；**
- **只有完成态证据通过严格验证后，才允许开始评分；**
- **Agent 行为失败不同于证据缺失、损坏或评测不可判定。**

因此，评测结果可以被重放和复核，也可以用于 CI 或发布决策，而无需让
Evaluator 接管 Agent Runtime。

## Cernora 在完整评测系统中的位置

Cernora 负责离线决策链路，不负责 Agent 执行或实验编排。外部 Runtime 产生
完成态导出，明确选择的 Adapter 将其规范化，Cernora 再完成验证、评分并输出
与证据绑定的 `GateDecision`。完整系统构成和精确组件职责见
[Architecture](docs/public/architecture.md)。

## 核心保证

- **运行时中立：** 评测已经完成的本地导出，不启动或管理 Agent。
- **证据绑定：** 通过明确的版本化契约和内容摘要，绑定 Profile、Case、
  fixture、artifact、Producer 和 Run 身份。
- **严格可重放：** 规范化 package 持久化后必须重新加载，才能接受结果。
- **Fail-closed：** 损坏、不完整或权威不兼容的证据永远不能变成 pass。
- **区分结果性质：** 将有效的行为失败与无效或不可判定的评测分开。
- **可移植：** 公开示例和 Profile 资源只依赖安装后的 wheel，不需要源码
  checkout、服务凭证或网络连接。

内容摘要可以检测字节变化，但不能认证 Producer 身份，也不提供不可否认性。

## 快速开始

### 1. 在虚拟环境中从 PyPI 安装

请使用 CPython 3.12 或 3.13。下面的命令先创建隔离环境，避免修改系统或包管理器
拥有的 Python；如果安装的是 Python 3.13，请把 `python3.12` 换成 `python3.13`：

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install cernora
cernora --version
```

发布维护者如需验证精确的本地产物，应使用[本地发布检查清单](docs/public/local-release-checklist.md)，
而不是上面的 PyPI 安装命令。

### 2. 运行打包的工作流示例

可以在任意目录执行：

```bash
python -m cernora.examples.offline_workflow ./cernora-offline-example
```

输出目录必须尚不存在。重复执行时，请改用新的路径，例如
`./cernora-offline-example-2`；Cernora 会拒绝覆盖已经完成的结果。

预期终态结果：

```text
pass
```

该示例从打包的合成 fixture 生成完成态导出，将其适配为 EvidenceBundle v2，
进行规范化导入、评测并严格重新加载结果。它不会启动 Agent、创建沙箱、捕获
runtime receipt，也不需要 Runtime 凭证。

### 3. 运行打包的 Coding Case

```bash
python -m cernora.examples.coding_task ./cernora-coding-example backend-v1
```

这个输出目录每次执行时也必须是全新的。

Coding 示例还包含 `frontend-v1` 和 `fail-closed-v1`。每个 Case 使用打包的
合成候选与完成态导出，把候选与终态证据绑定，并执行由 Evaluator 拥有的终止
后检查；它不会执行候选代码或启动 Agent。

## 决策语义

|结果|含义|
|---|---|
|`pass`|证据 eligible，并且所有必选观察都有效且满足要求。|
|`fail`|证据 eligible，并且证明存在行为不匹配。|
|`inconclusive`|证据、基础设施或评测权威缺失、损坏、不兼容或以其他方式无效。|

CLI 退出类别保持同样的区分：

|退出码|含义|
|---|---|
|`0`|命令成功，或评测结果 eligible 且 pass。|
|`1`|有效证据证明存在行为失败。|
|`2`|用法、选择或权威配置不兼容。|
|`3`|证据损坏、不完整、不可判定，或出现其他 fail-closed 评测错误。|

## Reference Profiles

|Profile|证明的能力|
|---|---|
|`offline-workflow`|精确工具选择、响应完整性，以及最终回答是否由受保护 fixture 证据支撑。|
|`coding-task`|候选格式与摘要绑定、终态绑定，以及覆盖后端、前端和 fail-closed Case 的 Evaluator 隐藏检查。|

这些 Profile 是中立的公开示例。Profile 定义版本化评测权威；用户应当选择
一个完整 Profile，而不是在运行时临时开关单项检查。

## 评测一个完成态导出

使用明确的内置 Profile 导入 EvidenceBundle v2：

```bash
cernora evidence import \
  --profile builtin:offline-workflow \
  --bundle ./completed-export/bundle.json \
  --output ./imported
```

评测严格持久化后的 import：

```bash
cernora evidence evaluate \
  --profile builtin:offline-workflow \
  --import-root ./imported \
  --output ./evaluated
```

Cernora `0.1.x` 只接受 EvidenceBundle v2/import v2，不转换或静默重解释旧版
Bundle 格式。

## Profile 与 Adapter SDK Preview

Preview SDK 只暴露两个刻意收窄的扩展点：

- `Profile` 定义权威、导入验证、Evidence 投影、评分观察和 Gate Policy；
- `Adapter` 把一个已经完成的原生导出转换为封闭、规范的 EvidenceBundle v2。

Adapter 永远不负责启动或重试 Agent、获取凭证、管理 sandbox 或执行 Runtime
清理。

Conformance helper 可以验证公开的静态契约：

```python
from cernora import check_adapter_conformance, check_profile_conformance
```

它们用于补充真实 import/evaluation 验收，不能代替真实验收。

### 默认私有的 Profile 编写目录

```bash
cernora profile init my-profile
cernora profile validate --profile-path .cernora/profiles/my-profile
```

Profile 默认创建在最近项目根目录下的 `.cernora/profiles/<name>/`。
`.cernora` 工作区包含自己的 `.gitignore`，降低私有 fixture 和策略被误
提交的风险。

只有明确指定其他目录时，才创建有意公开的 Profile：

```bash
cernora profile init public-profile --output profiles/public-profile
```

本地 Profile 通过 `profile.py:create_profile()` 显式加载，是受信任代码
执行。Cernora 不扫描 Profile、不维护注册中心、不修改 Git 状态，也不声称
能 sandbox 本地 Python。

## `0.1.0` 验证了什么

发布验收流程已经：

- 在仓库外的 Python 3.12 和 3.13 环境安装精确 wheel；
- 将工作流代表任务重复运行三次，并得到相同的规范结果；
- 将三个 Coding Case 分别重复运行三次；
- 严格重新加载 import 和 evaluation 结果 package；
- 拒绝损坏、缺失、权威不匹配和路径穿越证据；
- 对“有效证据证明行为不匹配”的情况保留 eligible `fail`；
- 使用封闭白名单扫描公开树、wheel 和源码归档。

详见[公开验收报告](docs/public/acceptance.md)及其
[机器可读摘要](docs/public/acceptance-summary.json)。

这些检查从打包的合成 completed export 开始，只证明 Cernora 评测内核链路；
不证明 Agent 启动、沙箱策略、可信 runtime receipt 捕获或 Experiment Harness
行为。

## 能力边界

Cernora `0.1.x` 是离线评测内核，不提供 Agent Runtime、实验调度器、托管服务、
注册中心、远程 Judge 或部署权威。
`1.0` 表示评测器 Contract 进入稳定状态，不表示 Cernora 会变成 Experiment
Harness。当前职责边界见
[Architecture](docs/public/architecture.md)，未来能力见
[产品路线图](ROADMAP.zh-CN.md)。

## 产品路线图

`0.1` 之后的第一优先级，是在现有 Profile/Scorer 归属模型下扩大确定性指标
覆盖；下一优先级是把 Profile Authoring 从 Scaffold 补到经过测试的首个
GateDecision。可复用的 `MetricPlan` 会后置到 Authoring、真实 Reference
Workflow 和重复实验已经证明该抽象之后。完整优先级、验收信号和明确不做事项
见双语[产品路线图](ROADMAP.zh-CN.md)。

## 文档

- [产品路线图](ROADMAP.zh-CN.md)
- [架构](docs/public/architecture.md)
- [Profile 编写](docs/public/profile-authoring.md)
- [Adapter conformance](docs/public/adapter-conformance.md)
- [兼容性矩阵](docs/public/compatibility-matrix.md)
- [Evidence 发布与重建](docs/public/evidence-publication-and-rebuild.md)
- [公开验收](docs/public/acceptance.md)
- [本地发布检查清单](docs/public/local-release-checklist.md)
- [正式发布日流程](docs/public/release-day-runbook.md)
- [变更记录](CHANGELOG.md)

## 贡献与安全

欢迎在已声明的 Runtime/Evaluator 边界内贡献代码。请先阅读
[CONTRIBUTING.md](CONTRIBUTING.md)。

不要在 Evidence 或公开 Profile 中放置密钥。应将本地 Profile Python 视为
以当前用户权限执行的代码。发现疑似漏洞时，请按照
[SECURITY.md](SECURITY.md) 中的流程报告。

## 许可证

Cernora 使用 [Apache License 2.0](LICENSE)。
