# Cernora

[English](README.md) | **简体中文**

[![CI](https://github.com/Yangyang96/cernora/actions/workflows/ci.yml/badge.svg)](https://github.com/Yangyang96/cernora/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/cernora)](https://pypi.org/project/cernora/)
[![Python](https://img.shields.io/pypi/pyversions/cernora)](https://pypi.org/project/cernora/)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)

> **面向已完成 AI Agent Run 的确定性离线评测与 CI 准出。**

Cernora 是一个独立评测内核，根据记录下来的工具调用、返回数据、产物和终态回答，
验证一个已完成的 Agent Run。它把完成态导出转换为 Evaluator 拥有的 `Evidence`、
`Score` 和 `GateDecision`，不启动 Agent、不相信 Runtime 对成功的自我声明，也不需要
网络访问。

以下场景适合使用 Cernora：

- 证明 Agent 使用了预期工具和参数，并且回答确实由返回证据支撑；
- 把冻结的 Agent 导出转换为可复现的回归测试或 CI/发布准出决策；
- 让评测权与 Runtime 的凭证、沙箱、重试和成功自述保持分离。

> **当前版本：** `0.1.0`，已在 Python 3.12 和 3.13 上测试。操作系统状态见
> [平台矩阵](docs/public/compatibility-matrix.zh-CN.md)。
>
> **本地发布候选：** `0.1.1`；此 checkout 尚未发布该版本。

## 五分钟运行 `0.1.1` 发布候选

Cernora 支持 CPython 3.12 和 3.13。

生产安装命令仍为 `python -m pip install cernora`。在 `0.1.1` 正式发布前，该命令安装的是
尚不包含以下两个示例的 `0.1.0`；请从仓库根目录使用下面的命令安装当前 checkout。

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install .

# 运行完整的工具工作流评测
python -m cernora.examples.tool_workflow ./cernora-workflow-run happy-path

# 运行打包的 Coding 评测
python -m cernora.examples.coding_evaluation ./cernora-coding-run happy-path
```

每个命令都会输出：

```text
pass
```

生成的 `GateDecision` 和 Preview `EvaluationReport` 会记录为什么通过。
Tool Workflow 示例包含等价于以下内容的结果：

```text
decision: pass
eligible: true
report:
  conclusion: pass
  evaluation_validity: valid
  required_results:
    task_outcome: true
    policy_compliance: true
  diagnostics:
    milestone_coverage: 1.0
    tool_calls: 3
```

每次运行的输出目录必须尚不存在。两个示例均可直接从安装后的 wheel 运行，使用
Profile-owned 合成 completed export，不需要凭证或源码 checkout，并会写入和严格重载
Preview `EvaluationReport`。它们验证冻结的评测语义，不证明真实外部动作或测试运行发生过。
Coding 示例还会报告 F2P/P2P 比率、构建状态、Candidate/Terminal Binding、Diff Policy、
篡改检查和 Retry Policy Compliance。

## 为什么需要 Cernora？

看起来正确的最终回答，不能证明 Agent 正确完成了任务。Agent 可能选择了错误工具、
传入错误参数、忽略工具返回、修改意外的产物，或在执行环境失败后仍报告成功。

Cernora 把评测设计成独立的裁决权威：

- **Runtime** 负责执行、凭证、沙箱、重试和证据捕获；
- **Adapter** 把一个已完成的原生导出转换为封闭的 `EvidenceBundle v2`；
- 版本化 **Profile** 验证证据并定义必选观察；
- Cernora 输出可复现、且 Runtime 不能自行授予的决策。

![Cernora 将 Producer 拥有的 Agent 执行与 Evaluator 拥有的证据验证、评分和准出决策分离。](docs/assets/cernora-architecture.jpg)

组件职责和信任边界见[架构文档](docs/public/architecture.zh-CN.md)。

## 明确区分失败性质

|决策|含义|
|---|---|
|`pass`|证据 eligible，且所有必选观察都有效并满足要求。|
|`fail`|证据 eligible，且证明存在 Agent 行为不匹配。|
|`inconclusive`|证据、基础设施或评测权威缺失、损坏或不兼容。|

基础设施故障不会被伪装成 Agent 失败，无法验证的证据也永远不能变成 pass。CLI
退出码保持相同语义：`0` 为 pass，`1` 为行为失败，`2` 为用法/权威不兼容，
`3` 为无效或不可判定的评测。

## 工程设计亮点

- **严格的版本化契约：** Pydantic 模型和公开 JSON Schema 拒绝未知字段、不支持的
  版本、身份不一致、不安全路径和无效摘要。
- **证据与权威绑定：** Producer、Run、Profile、Case、fixture 和 artifact 身份会
  一直绑定到最终决策。
- **确定性重放：** canonical JSON、内容摘要、原子发布和持久化结果严格 reload，
  让重复评测可复核。
- **Fail-closed 组合：** 只有 import eligibility 成立后才开始评分；缺失或无效观察
  不能静默通过。
- **收窄的扩展接口：** 显式 `Adapter` 和 `Profile` 协议允许接入新 Runtime 和评测
  策略，而不把 Cernora 变成执行框架。
- **发布工程：** CI 覆盖 Python 3.12/3.13、测试、lint、format、严格类型检查、
  distribution 检查和源码仓库外的 wheel-only 验收。

内容摘要只能证明字节完整性，不能认证 Producer 身份，也不提供不可否认性或不可变历史。

## Reference Evaluations

|Profile|证明的能力|
|---|---|
|`offline-workflow`|精确工具/参数选择、响应完整性，以及回答是否由受保护 fixture 证据支撑。|
|`coding-task`|候选导出格式、内容和终态摘要绑定，以及覆盖 backend、frontend 和 fail-closed Case 的 Evaluator post-terminal checks。|
|`tool-workflow`|针对有状态合成工作流的 outcome-first structured result，绑定精确 Profile-owned observation；不证明真实外部动作已发生。|
|`coding-evaluation`|针对精确 Profile-owned 合成 capsule，验证 Candidate Tree v1 重建、F2P/P2P、build/回归结果、派生 diff policy、篡改检查和终态绑定。|

Profile 是完整且版本化的策略。评测时不能临时关闭单项观察，因此相同证据和权威会得到
相同语义。
两个新增 Profile 都是显式选择的参考实现；加入它们不会改变既有 Profile 的行为，也不会
让其他 Profile 自动生成 Structured Report。

## 评测自己的完成态导出

下面的命令复用“五分钟运行”生成的 `EvidenceBundle v2`，再评测严格持久化后的
package。评测自己的 Run 时，请把 `--bundle` 替换为 Adapter 生成的 bundle 路径，
并在两个命令中选择与之匹配的 Profile：

```bash
cernora evidence import \
  --profile builtin:tool-workflow \
  --bundle ./cernora-workflow-run/bundle/bundle.json \
  --output ./imported

cernora evidence evaluate \
  --profile builtin:tool-workflow \
  --import-root ./imported \
  --output ./evaluated
```

Cernora `0.1.x` 只接受 EvidenceBundle v2/import v2，不会静默转换或重新解释旧格式。

## 扩展 Cernora

Preview SDK 只暴露两个刻意收窄的扩展点：

- `Profile` 定义权威、import validation、Evidence 投影、观察和 Gate Policy；
- `Adapter` 把一个已完成的原生导出转换为 canonical `EvidenceBundle v2`。

```python
from cernora import check_adapter_conformance, check_profile_conformance
```

创建默认私有的 Profile 工作区：

```bash
cernora profile init my-profile
cernora profile validate --profile-path .cernora/profiles/my-profile
```

本地 Profile 是显式加载的受信任 Python 代码。Cernora 不扫描插件、不修改 Git 状态，
也不声称 sandbox Profile 执行。详见 [Profile 编写](docs/public/profile-authoring.zh-CN.md)和
[Adapter conformance](docs/public/adapter-conformance.zh-CN.md)。

## `0.1.1` 发布候选已验证内容

公开验收流程在源码仓库外的 Python 3.12 和 3.13 环境中安装精确 wheel。除原有代表任务
外，它还验收全部 18 个 `tool-workflow` 场景和 20 个 `coding-evaluation` 场景；每个可接受
场景都运行三次，结果 byte-identical 且可严格 reload。无效权威、损坏输入和路径边界场景
都会 fail closed，
而有效证据证明的错误行为会保留为 eligible `fail`。

查看[验收报告](docs/public/acceptance.zh-CN.md)和
[机器可读摘要](docs/public/acceptance-summary.json)。重建验收证据前，先激活一个已安装
精确构建 wheel 的干净 Python 3.12 或 3.13 环境；然后从仓库根目录执行以下命令，
在 checkout 外运行脚本并比对摘要：

```bash
repo_root=$PWD
acceptance_root=$(mktemp -d)
cd "$acceptance_root"
env -u PYTHONPATH PYTHONNOUSERSITE=1 \
  python "$repo_root/scripts/rebuild_acceptance.py" \
  --output ./cernora-public-acceptance
cmp ./cernora-public-acceptance/summary.json \
  "$repo_root/docs/public/acceptance-summary.json"
```

## 什么时候使用 Cernora

Cernora 位于 Agent Runtime 完成一次 Run 之后。它是完整 Agent 评测系统中的独立
裁决层，不替代执行或可观测系统：

|如果你需要……|应使用……|
|---|---|
|运行 Agent、管理沙箱、调度数据集或执行基础设施重试|Agent Runtime 或 Experiment Harness|
|通过大量指标比较 Prompt|专注实验和 Scorer 的评测框架|
|采集、查询生产 Trace|可观测平台|
|验证完成态导出并给出证据绑定的准出决策|**Cernora**|

`0.1.x` 不提供 Agent Runtime、调度器、托管服务、注册中心、远程 Judge、部署权威或
可信 runtime receipt 捕获；这些属于 Runtime 或 Experiment Harness。上述内容是明确的
架构边界，而不是暗示存在的能力。后续计划见[产品路线图](ROADMAP.zh-CN.md)。

## 文档

- [中文文档索引](docs/public/README.zh-CN.md)
- [架构](docs/public/architecture.zh-CN.md)
- [Profile 编写](docs/public/profile-authoring.zh-CN.md)
- [Adapter conformance](docs/public/adapter-conformance.zh-CN.md)
- [兼容性矩阵](docs/public/compatibility-matrix.zh-CN.md)
- [Evidence 发布与重建](docs/public/evidence-publication-and-rebuild.zh-CN.md)
- [公开验收](docs/public/acceptance.zh-CN.md)
- [本地发布检查清单](docs/public/local-release-checklist.zh-CN.md)
- [正式发布日流程](docs/public/release-day-runbook.zh-CN.md)
- [变更记录](CHANGELOG.zh-CN.md)

## 贡献、安全与许可证

欢迎在已声明的 Runtime/Evaluator 边界内贡献代码。请先阅读
[中文贡献指南](CONTRIBUTING.zh-CN.md)。不要在 Evidence 或公开 Profile 中放入密钥；
疑似漏洞请按[中文安全策略](SECURITY.zh-CN.md)中的流程报告。

Cernora 使用 [Apache License 2.0](LICENSE)。
