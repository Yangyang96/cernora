# Cernora

[English](README.md) | **简体中文**

[![CI](https://github.com/Yangyang96/cernora/actions/workflows/ci.yml/badge.svg)](https://github.com/Yangyang96/cernora/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/cernora)](https://pypi.org/project/cernora/)
[![Python](https://img.shields.io/pypi/pyversions/cernora)](https://pypi.org/project/cernora/)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)

> **面向工具型 Agent 的证据绑定评测。**

Cernora 是一个面向已完成 Agent Run 的独立评测内核，具有确定性且运行时中立。
这个 Python 包把完成态导出转换为 Evaluator 拥有的 `Evidence`、`Score` 和
`GateDecision`，不启动 Agent、不相信 Agent 对成功的自我声明，也不需要网络访问。

> **当前版本：** `0.1.0`，已在 Python 3.12 和 3.13 上测试。操作系统状态见
> [平台矩阵](docs/public/compatibility-matrix.zh-CN.md)。

![Cernora 将 Producer 拥有的 Agent 执行与 Evaluator 拥有的证据验证、评分和准出决策分离。](docs/assets/cernora-architecture.jpg)

## 它解决什么问题

看起来正确的最终回答，不能证明 Agent 正确完成了任务。Agent 可能选择了错误工具、
传入错误参数、忽略工具返回、修改意外的产物，或在执行环境失败后仍报告成功。

Cernora 把评测设计成独立的裁决权威：

- **Runtime** 负责执行、凭证、沙箱、重试和证据捕获；
- **Adapter** 把一个已完成的原生导出转换为封闭的 `EvidenceBundle v2`；
- 版本化 **Profile** 验证证据并定义必选观察；
- Cernora 输出可复现、且 Runtime 不能自行授予的决策。

因此，结果可用于离线复核、回归测试以及 CI/发布准出。

## 五分钟运行

Cernora 支持 CPython 3.12 和 3.13。

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install cernora

# 运行完整的工具工作流评测
python -m cernora.examples.offline_workflow ./cernora-workflow-run

# 运行打包的 Coding 评测
python -m cernora.examples.coding_task ./cernora-coding-run backend-v1
```

每个命令都会输出：

```text
pass
```

每次运行的输出目录必须尚不存在。两个示例均可直接从安装后的 wheel 运行，使用合成的
completed export，不需要凭证或源码 checkout。

## 明确区分失败性质

|决策|含义|
|---|---|
|`pass`|证据 eligible，且所有必选观察都有效并满足要求。|
|`fail`|证据 eligible，且证明存在 Agent 行为不匹配。|
|`inconclusive`|证据、基础设施或评测权威缺失、损坏或不兼容。|

基础设施故障不会被伪装成 Agent 失败，无法验证的证据也永远不能变成 pass。CLI
退出码保持相同语义：`0` 为 pass，`1` 为行为失败，`2` 为用法/权威不兼容，
`3` 为无效或不可判定的评测。

## 架构与信任边界

执行权与裁决权刻意保持独立。组件职责和信任边界见
[架构文档](docs/public/architecture.zh-CN.md)。

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

Profile 是完整且版本化的策略。评测时不能临时关闭单项观察，因此相同证据和权威会得到
相同语义。

## 评测自己的完成态导出

先导入 `EvidenceBundle v2`，再评测严格持久化后的 package：

```bash
cernora evidence import \
  --profile builtin:offline-workflow \
  --bundle ./completed-export/bundle.json \
  --output ./imported

cernora evidence evaluate \
  --profile builtin:offline-workflow \
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

## `0.1.0` 已验证内容

公开验收流程在源码仓库外的 Python 3.12 和 3.13 环境中安装精确 wheel，将 workflow
代表任务运行三次，并将三个 Coding Case 分别运行三次；结果保持 byte-identical，
且都经过严格 reload。验收还确认：损坏或缺失 artifact、权威不一致和候选路径穿越会被
拒绝，而有效证据证明的错误行为会保留为 eligible `fail`。

查看[验收报告](docs/public/acceptance.zh-CN.md)和
[机器可读摘要](docs/public/acceptance-summary.json)，
或重建验收证据：

```bash
uv run python scripts/rebuild_acceptance.py --output ./cernora-public-acceptance
```

## 定位与能力边界

Cernora 是完整 Agent 评测系统中的独立裁决层：

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
