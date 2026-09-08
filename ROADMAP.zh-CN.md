# Cernora 产品路线图

[English](ROADMAP.md) | **简体中文**

本文只负责说明 Cernora 在 `0.1` 发布后的产品优先级。使用方式请从
[README](README.zh-CN.md) 开始；当前组件边界与不变量请参阅
[Architecture](docs/public/architecture.md)。

Cernora 将继续保持为离线、运行时中立的评测内核。后续能力应当让真实评测更
容易组合、比较和消费，但不会把 Agent 执行、凭证、沙箱或部署权威移入内核。
`1.0` 改变的是 Cernora Contract 的成熟度，不会改变这条职责边界。

## Adapter 术语

本路线图区分两种性质不同的 Adapter：

- **Evidence Adapter：** Cernora 的扩展接口，读取一个已经完成的原生导出，并
  生成封闭的 EvidenceBundle v2。它在 `0.1.x` 中是 Preview，并计划成为
  Stable `1.0` Core 的一部分。
- **Runtime Connector：** 由外部 Experiment Harness
  使用的 Runtime-specific Companion，负责运行 Agent 并冻结完成态导出。它始终
  位于 Cernora Core 之外；只有两个具体集成证明了同一个收窄 Contract 后，才会
  提炼通用接口。

Roadmap 中的 Runtime Connector 永远不表示 `cernora` Package 会成为通用 Agent
Runner，也不表示它会接管凭证、Sandbox 或进程所有权。

## 优先级顺序

当前主线是 **P4 收尾 → P4.5 真实场景正向提升 → Chora 最小接入**。
项目首先服务于 Agent 评测研发实践、external-tool CLI 的实际改进和 Chora 完成态任务评测。
通用性从这些用法中提炼；不以追平成熟评测平台的功能覆盖作为完成条件。

| 顺序 | 里程碑 | 当前安排 |
| --- | --- | --- |
| P1–P3 | 指标、Profile Authoring、Reference Workflow | 保留已交付能力与兼容边界。 |
| P4 | 批量实验、比较与证据闭环 | 72 Trials 已完成，负向结果与离线重建已封存；公开发布单独跟踪。 |
| P4.5 | external-tool CLI 真实场景正向提升 | 下一项工作；必要时引入经人工校准的最小辅助 Judge。 |
| 随后 | Chora 最小接入 | 先接一类完成态任务，保存并展示可追溯的评测结论。 |
| 原 P5 | Metric SDK / `MetricPlan` | 条件储备：多个真实 Profile 暴露重复需求后再启动。 |
| 原 P6 | 第二个 Producer / Runtime Connector | 条件储备：两个具体集成证明共同需求后再抽象。 |
| 原 P7 / P8 | 通用 LLM Judge / 稳定化 | 条件储备：真实评分需求驱动，不阻塞 P4.5 的辅助 Judge。 |
| 原 P9 | Gate Consumer / Provenance | 条件储备：真实消费方需要分阶段 Gate 时启动。 |
| `1.0` | 稳定公共边界 | 长期成熟度目标，不作为当前两个应用里程碑的前置条件。 |

保留原 P5–P9 编号与设计供追溯，它们不再表示必须依次执行的排期。
只有当前消费者确有需求时才增加接口；每个阶段结束时删除被替代的实现和一次性工具，
保留复现所需的历史源码及证据，不再单独开启无边界的清理或框架扩建。

## `0.1.x` 基线

本路线图从已经发布的离线评测内核开始，它已经提供：

- 从 Completed Export 到 EvidenceBundle v2、规范导入、Evidence、Score 和
  GateDecision 的完整链路；
- 严格验证、Authority Binding、Fail-closed Decision、Atomic Persistence 与
  Strict Reload；
- Wheel 内置的离线工作流和 Coding 示例，可以在源码 Checkout 之外运行；
- 边界收窄的 Profile 与 Evidence Adapter SDK Preview；
- 默认位于 `.cernora/profiles/` 下的私有 Profile Scaffold、显式受信任加载与
  静态 Conformance Validation。

`0.1.x` 只接受 EvidenceBundle v2/import v2，并继续使用 Evidence v1、Score v1
和 GateDecision v1 作为当前输出协议。精确兼容承诺以 Compatibility Matrix 为准。

已发布的 `0.1.1` 还提供显式选择的 Preview ResultRecord v1、EvaluationReport v1，
以及 `tool-workflow` 和 `coding-evaluation` 参考 Profile；它不改变已发布 `0.1.0` 的默认行为。

有用的确定性指标覆盖是 `0.1` 之后的第一项能力；随后补齐 Profile Authoring
Loop，让第三方能够端到端证明自己的 Assessment。公共 `MetricPlan` 会刻意后置：
先由 Authoring、真实工作流和实验结果塑造抽象，再将它冻结为接口。

## 优先级 1——确定性指标覆盖

**状态：** 已在 `0.1.1` 中实现并发布，采用显式选择的 Preview Result Report。
优先级 2 已在 `0.1.2` 中实现并发布。

已接受的实现基线见
[`docs/design/priority-1-deterministic-metrics.md`](docs/design/priority-1-deterministic-metrics.md)。
`coding-evaluation` 只在独立 Coding evidence review 冻结 candidate reconstruction、
合成执行权威、测试分类、篡改和 change-policy 语义后实现。

### 目标

在初始 Profile 自有布尔 Observation 之外增加有用、可由证据推导的指标，同时
保持确定性重放和已经接受的 Score v1 Contract。

本阶段改善 Cernora“能测什么”，并不要求同时提供通用 Metric SDK 或公共
`MetricPlan`。在真实工作流证明稳定的复用形态之前，指标选择与 Gate Policy
可以继续由各 Profile 显式拥有。

### 指标模型

|层级|范围|Gate 用途|
|---|---|---|
|Outcome 或 Constraint|单个 Completed Run；布尔、证据绑定，并由 Score Policy 要求。|映射必选 Observation 并参与 `GateDecision`。|
|Advisory|单个 Completed Run；重要但不阻断。|突出报告，默认不阻断。|
|Diagnostic|单个 Completed Run；布尔、数值或分类结果，带 Validity；数值还带 Unit 和 Direction。|只用于分析和比较。|

### 已交付覆盖

- **工具工作流：** Tool Selection、Argument Accuracy、Sequence Adherence、
  Result Grounding、Recovery、Idempotency 和 Forbidden Action。
- **Coding：** Build/Test 结果、Candidate Digest 与 Terminal Binding、Diff
  Scope、Regression、Test Tampering 和 Forbidden-file Change。
- **可靠性与安全：** Evidence Validity 与 Completeness、Malformed Input、
  Timeout 与 Infrastructure Failure、Repeated Side Effect 和 Forbidden Action。
- **效率：** Profile-owned Tool Workflow 证据提供 Latency、Step、Tool Call、Retry
  和 Side Effect。Token 用量、成本和 Cost-per-success 等 Completed Export 能提供
  可信数值后再实现。

每项结果具有明确 Identity、Version、Value Type、适用时的 Unit 与
Direction、Validity State、Failure Reason，以及支撑它的 Evidence Reference。
新的诊断数据会先进入独立、版本化的 Preview Report，而不会在 `0.1.x` 中静默
修改 Score v1。

Core Evidence Invariant 不是 Metric。Schema/Version Validation、Bundle 与
Artifact Digest、Authority Binding、Contained Path、Conflict-safe Publication
和 Strict Reload 始终先执行，Profile 不能降低其优先级。

### 指标准入规则

指标必须可行动、由证据推导、可复现、显式版本化，并由 Profile 或 Report
Contract 管理；还必须定义输入缺失、无效、矛盾和不可用时的行为。不会仅为了
增加指标数量而加入 Metric。

### `0.1.1` 已交付内容

本阶段先用 Profile-owned 实现证明指标语义，不提前暴露通用 `Metric` 接口：

1. **结果记录：** 为每项 Observation/Measurement 输出版本化记录，至少包含
   `id`、`version`、`role`、`value`、`value_type`、`validity`、`failure_reason` 与
   `evidence_refs`；数值项再声明 `unit` 与 `direction`。
2. **Tool Workflow 包：** 先实现 Tool Selection、Argument、Sequence、Grounding、
   Recovery、Idempotency 与 Forbidden Action，并为乱序、错误参数、伪造结果和
   重复副作用提供合成负向 Fixture。
3. **Coding 包：** 先实现 Build/Test、Candidate/Terminal Binding、Diff Scope、
   Regression、Test Tampering 与 Forbidden-file Change；所有行为结论都针对重建后
   的确切 Candidate，而不是 Agent 的声明。
4. **可靠性与效率报告：** 输出 Validity 与 Infrastructure Failure，并单独报告 Tool
   Workflow 的 Latency、Step、Tool Call、Retry 与 Side Effect；缺失或不可信的计量值
   显示为不可用，不按零处理。Token 与 Cost 指标仍未实现。
5. **Profile 验收：** 同一冻结输入重复三次得到字节稳定的确定性结果，并覆盖
   真值、行为假值、证据缺失、证据矛盾和基础设施不可用。

Required Observation 只有在输入有效时才能产生行为 `pass` 或 `fail`。输入缺失、
无效或互相矛盾必须保持 `inconclusive`；Diagnostic Measurement 永远不能把 Required
Failure 抵消为通过。本阶段也不产生跨指标的任意加权总分。

### 完成证据

`tool-workflow` 与 `coding-evaluation` Profile 能从冻结 Evidence Package 生成 Required
Gate Observation 和更丰富的诊断。已接受矩阵会让每个有效输入重复运行三次并得到
byte-identical 输出，且无效 Evidence 不能变成 pass。

## 优先级 2——完整 Profile Authoring Loop

**状态：** 已在 `0.1.2` 中实现并发布。后续实验状态见优先级 4。

### 目标

把 `0.1.x` Profile SDK Preview 从安全的起始 Scaffold 补成完整、Wheel-only 的
编写流程。第三方无需阅读 Cernora 内部实现或复制内置 Profile，就能创建私有
Profile、实现一个确定性 Assessment，并证明三种结果类别。

`0.1.x` 已经提供默认私有的 `profile init`、显式
`profile.py:create_profile()` 加载、静态 Conformance Validation，以及 Import/
Evaluate 的 `--profile-path` 选择。生成的 `assess()` 会有意 Fail Closed，直到
作者完成实现；静态校验本身不能证明评测行为正确。

### 计划内容

- 提供带指导的最小模板，包含 Authority、一个 Case、Fixture、一个 Required
  Observation 和一种 Completed-export Shape；
- 继续让生成的默认实现 Fail Closed，同时明确实现步骤和 Authority Version
  变更要求；
- 增加有文档的 Profile Test Workflow，通过真实 Import、Evaluation 与 Strict
  Reload 运行有效 Pass、行为 Fail 和 Invalid/Inconclusive Case；
- 生成或打包 Evidence 缺失、损坏和 Authority Mismatch 的合成 Fixture，不暴露
  私有数据；
- 验证重复结果确定性，以及不存在未声明的网络、凭证和仓库根目录依赖；
- 改进 Invalid Authority、Missing Observation、Malformed Evidence Reference
  和 Scorer/Gate Policy Mismatch 的诊断；
- 展示 `MetricPlan` 出现前 Profile 如何拥有确定性 Observation，并给出后续迁移
  到共享 Metric SDK 的路径；
- 保持 `.cernora/profiles/` 默认私有和显式公共放置；
- 不增加 Profile Discovery、Publish/Promote 自动化、注册中心或市场。

### 作者工作流

```text
cernora profile init <name>
    -> .cernora/profiles/<name>/
    -> 实现 profile.py:create_profile()
    -> cernora profile validate --profile-path ...
    -> 运行 pass / fail / inconclusive 合成 Case
    -> Import + Evaluate + Strict Reload
    -> 冻结 Profile Authority Version
```

最小目录包含 `profile.py`、`profile.json`、`cases/`、`fixtures/` 和本地测试。模板会
解释每个文件的 Authority 作用、哪些变化必须升级 Profile Version，以及为什么
本地 Python Profile 是显式受信任代码而不是 Sandbox。

### 交付切片

1. **Guided Scaffold：** 一个可实现的最小 Assessment、注释化 Fixture 和
   Fail-closed 默认行为。
2. **Behavior Test Command：** 用同一条公开命令执行静态 Conformance 与真实
   Import/Evaluate/Reload，不把“能加载”误当成“能正确评测”。
3. **Negative Fixture Pack：** Missing Evidence、Malformed Reference、Authority
   Mismatch、Scorer/Gate Policy Mismatch 与非确定性结果。
4. **Wheel-only Tutorial：** 在空项目中只安装 Wheel，创建私有 Profile，并在
   不访问源码树的情况下完成三类结果。
5. **Migration Note：** 当 `MetricPlan` Preview 可用后，展示如何逐项迁移已有
   Observation；迁移前后的 Authority 与 Decision 不得被静默重解释。

### 完成信号

第三方从干净项目中安装 Wheel 后，可以运行 `profile init`、实现一个小型领域
检查、完成校验，并通过 Strict Reload Result 覆盖 pass/fail/inconclusive；所有
Profile Source 和 Fixture 默认保持私有。

## 优先级 3——公开 Reference Evaluation Workflow

**状态：** 已于 2026-08-25 在独立 Companion Workflow 中完成。已经冻结的 Harness、
Runtime、格式、Vertical Tracer、Authority 边界、失败策略、发布 Gate 与交接记录位于
[`docs/design/priority-3-reference-workflow.md`](docs/design/priority-3-reference-workflow.md)。

### 目标

证明已发布 Package 可以评测真实外部 Agent Runtime 产生的证据，同时继续把
Runtime 的所有权保持在 Cernora 之外。

### Companion Project

这条工作流放在独立 Companion Repository 中，暂定名
`cernora-reference-workflow`。它像第三方一样安装已经发布的 `cernora`
Distribution，不导入 Cernora 源码 Checkout。独立仓库既能证明公共 Package
边界，也能避免 Runtime Dependency 进入 Core。

### Reference Architecture

```text
ExperimentSpec
    -> 薄 Experiment Harness
    -> 具体 Runtime Connector
    -> 外部 Agent Runtime
    -> 冻结 Completed Export
    -> 离线 Evidence Adapter
    -> EvidenceBundle v2
    -> Cernora Import + Evaluate + Strict Reload
    -> 单 Run Decision
    -> 可移植 Run Report
```

第一个 Connector 使用一个精确固定版本的开源 Container-agent Harness 与一个精确
固定版本的外部 Agent Runtime。Harness 负责任务与 Container Lifecycle、Trial 和原始
Artifact 收集；Cernora 不重建这些能力。精确依赖、版本与许可证记录放在 Companion
Repository 中；Cernora Core 和本 Contract 继续保持 Runtime-vendor Neutral。

### `ExperimentSpec`

每个实验冻结：

- Schema Identity 与基于内容生成的 Experiment Identity；
- Task、Prompt、Path Policy 与 Container Image Digest；
- Harness、Runtime、模型与 Reasoning Configuration 的精确版本；
- Timeout、Resource、Provider Egress、Web Search 与 Retry Policy；
- Test Runner Plan 与 Companion Profile Authority；
- Exporter、Adapter、Report 和 Cernora Wheel 的版本与 Digest。

其中任何数值发生变化，都产生新的 Experiment Identity，不能静默修改已有 Run。
Credential、Account Identifier、Host Path、Timestamp、随机 Identifier 和物理 Output
Root 不进入身份。

### 薄 Harness 职责

Companion Harness 只负责：

- 校验并解析冻结的 ExperimentSpec；
- 调用固定版本的 Harness/Runtime Integration；
- 跟踪 Trial Lifecycle 并保留每一次 Attempt；
- 按冻结 Policy 重试符合条件的 Infrastructure Failure；
- 调用 Evidence Adapter 与已发布 Cernora CLI/API；
- 保留不可变的单 Run Decision，但不重写它们；
- 生成机器可读 Manifest 与可移植 Run Report。

Runtime Connector 调用一个具体外部 Runtime、等待终态并返回 Runtime-owned
Output。Completed Exporter 随后冻结终态、Tool Call、日志、Candidate Artifact、
Resource Measurement、Receipt，以及带内容摘要的 Artifact Manifest。离线 Evidence
Adapter 只把这个冻结目录转换为 EvidenceBundle v2。

### Authority 与 Retry 规则

- 外部 Harness Reward 或 Verifier Result 可以作为 Producer-side Diagnostic
  Evidence 保留，但永远不是 Cernora Pass 或 GateDecision；
- 行为 `fail` 是完成结果，不能通过反复 Retry 让它消失；
- Infrastructure Retry 必须保留失败 Attempt，并记录为什么允许新 Attempt；
- Export 数据缺失、损坏或矛盾时得到 `inconclusive`，聚合不能从分母中删除
  Invalid Run；
- Baseline 在本地运行，关闭可选 Upload/Telemetry，不使用托管 Dashboard 或
  Registry；
- Secret 继续由 Runtime 拥有，不能进入 Completed Export、EvidenceBundle、
  Report 或 Cernora Configuration。

### 最小公共范围

- 一个合成 Python 修复任务 `tiny-calculator-v1`，包含两个 Fail-to-pass 与两个
  Pass-to-pass Test；
- 一个固定版本的 Container Harness、一个固定版本的外部 Runtime、模型
  `gpt-5.6-terra`、`medium` Reasoning，以及一种严格的 `completed-export/v1` 格式；
- 一个显式离线 Evidence Adapter 与 Companion-owned
  `cernora-reference-coding-v1` Profile；
- 真实 `pass`、行为 `fail`、Timeout 和 Interruption Attempt；
- Missing Artifact、Digest Mismatch、Authority Mismatch 与 Fake-secret Rejection 的
  确定性派生 Fixture；
- Candidate、Terminal、Test Runner Receipt 与 Artifact 绑定；
- 对同一冻结 Export 做三次 Byte-identical Evaluation；
- 可移植 Result Manifest 与紧凑 Run Report。

### 交付切片

1. **Release Baseline 与格式：** 验证公共 `0.1.2` Wheel，再实现严格的
   `experiment-spec/v1` 与 `completed-export/v1` Contract。
2. **Compatibility Spike：** 验证固定版本 Harness/Runtime、Subscription Auth、
   Telemetry Setting、Provider Egress、Artifact Location 与 Cleanup。
3. **Vertical Tracer：** 一个任务、一个外部 Run、一个冻结 Export 和一个 Strict
   Reload GateDecision。
4. **Failure Matrix：** 真实 Lifecycle Failure，加上明确标注、确定性生成的
   Corruption 与 Authority-mismatch Fixture。
5. **Determinism 与 Report：** 同一冻结 Export 评测三次并得到 Byte-identical
   Result，同时提供精确的离线重建说明。
6. **Private Publication Gate：** Conformance、Secret、License 与 Native-platform
   Gate 全部通过后才发布 Companion。

第一个集成会有意保持具体。应先用它发现 Runtime Producer 与离线评测之间的
真实接口，再考虑通用 Runtime Connector。

### 完成信号

一个干净项目可以从公共 Package Index 安装 Cernora，通过配套 Harness 运行
真实外部 Agent，冻结导出，并在不访问 Cernora 仓库的情况下重现相同的
Evaluator-owned Decision。另一个用户可以重新执行冻结的 `ExperimentSpec`、
检查每次 Attempt，并从机器可读 Artifact 重建已发布报告。

### 边界

配套 Harness 与 Runtime Connector 不是 Cernora Core。Cernora 不负责启动、
认证、重试、Sandbox、监督或清理 Agent。本阶段不建设通用 Queue、Cloud
Scheduler、多 Runtime Framework、托管服务或 Dashboard。

## 优先级 4——批量实验、报告与改进闭环

**状态（2026-09-09）：** 批次摘要与受控比较已实现，72 Trials / 72 Attempts 已完成，
无重试。18 pass、33 behavioral_fail、0 evaluation_invalid、21 infrastructure_unavailable。
Held-out RSR：baseline 8/9、candidate 1/9，结论为 `regressed`；Guardrail 尚不能支持晋级。
历史工具链和证据已本地封存，两次历史 wheel 离线重建各有 702 个文件逐字节一致。
这证明工程与证据链路可用，未证明正向提升，也不代表已经公开发布。

收尾事实、清理验证与剩余限制见 [P4 收尾记录](docs/p4-closeout.md)。原始设计见
[批量实验设计](docs/design/priority-4-batch-experiments.md)。

### 目标

将单次决策扩展为跨任务集、Runtime 版本和 Workflow 变更的可复现比较，并用
比较结果指导改进。

### 计划内容

- 定义可移植的 Batch Input 与 Result Summary 格式；
- 在每个实验身份中冻结 Runtime、模型、Prompt、Tool Schema、配置、Profile、
  Dataset 和重复次数；
- 分别计算 Evaluation Validity Rate、Behavioral Success Rate 和 Reliable
  Success Rate；
- Aggregate Metric 保持在 Batch Report 中，不会静默成为单 Run Gate；
- 在统计上合理时增加重复稳定性、Pass-at-k、置信区间和失败分布；
- 在质量与可靠性之外报告时延、Step、Tool Call、Retry、Token 用量、总成本
  和 Cost-per-success；
- 保留所有 Invalid 或 Inconclusive Run，不从平均值中删除；
- 为 CI 和外部可视化发布机器可读报告；
- 建立可重复的改进闭环：
  `冻结基线 -> 失败分类 -> 定向干预 -> 回归集 -> 隐藏集复测`；
- 比较干预措施时，不在实验中途改变评测策略。

Failure Taxonomy 将区分 Planning、Tool Selection、Argument、Sequence、
Grounding、Recovery、Behavioral Mismatch、Safety Violation，以及 Infrastructure
或 Evaluation Failure。

### Batch Artifact

每次批量实验至少产生以下可移植文件：

- `run-plan`：包装不可变的 P3 单 Run ExperimentSpec，并冻结精确的
  Case × Configuration × Repetition 槽位、执行策略和 Budget；
- `execution-manifest` 与 `trial-manifest`：将一次真实 Execution 及每个计划 Trial
  绑定到其 Append-only Attempt Chain；
- `attempt-manifest`：保留每次 Attempt、终态、重试资格和关联的单 Run Artifact；
- `run-results`：逐 Run 保存 Strict-reloaded Decision、Validity 与 Measurement；
- `batch-summary`：只从前述不可变结果派生 Aggregate、区间、Failure Distribution
  与重建信息。

两个实验只有在 Dataset/Case、Profile、Metric/Report Contract、Gate Policy、资源限制
和 Retry Policy 相同时才能生成 Controlled Comparison。每项允许的模型、Prompt、Tool
Schema 或 Runtime Treatment 都必须显示在 Comparison Manifest 中；其他组合只能生成
描述性的 `not_comparable` Report。行为失败不重试；Infrastructure Retry 保留原
Attempt；任何 Invalid Run 都同时进入总数与 Validity 统计，禁止挑选最好一次作为结果。

### Milestone（原始设计与当前状态）

1. **Companion Repeat Runner：** 实现已经完成；围绕冻结的
   Case × Configuration × Repetition Matrix、Append-only Attempt、Budget 与严格完整性
   实现 Run、Resume 和离线 Rebuild。已确认的 M1 基线保留 P3 `ExperimentSpec v1`，
   新增内容寻址的 `RunPlan v1`，在执行前冻结全部 Trial 槽位，顺序运行 Reference
   Acceptance，且不发布 Aggregate Quality 结论；Runtime Scheduling 继续位于 Core
   之外。已批准的原生退出门禁有意强于最初最低要求：12 个顺序 Trial、真实 Evaluated
   与 Unavailable Lifecycle Evidence、Graceful Stop/Resume、Closed Pack，以及无凭据的
   Byte-identical Rebuild。详见
   [`docs/design/priority-4-batch-experiments.md`](docs/design/priority-4-batch-experiments.md#milestone-1-approved-baseline)。
2. **Core Validity-first Batch Summary Preview：** 已在本地实现并验证；消费 Strict-reloaded Evaluation Package，报告 Trial-level
   Validity、Behavioral Success、Reliable Success，以及强制 Attempt Diagnostic。
3. **Core Controlled Comparison Preview：** 强制 Comparison Invariant、预声明
   Treatment、Primary Outcome 与 Guardrail；报告原始 Case Delta、确定性配对区间、
   符合条件的 Pass-at-k、Failure Migration 与 Efficiency Trade-off。
4. **Improvement Loop Proof 与 Evidence Release：** 原设计为 9 个 Case、54 个 Trial；
   实际完成 72 Trials，并封存负向结果与可离线重建的 Evidence Pack。公开 Evidence
   Release 单独待办；原始验收条款不因本地封存而自动满足。

### 完成信号

两个冻结配置能够通过有文档、可重复的流程比较，展示质量、可靠性、安全性、效率、
不确定性和回归。公开 Companion 针对 Regression/Held-out Case 完成一次诚实的干预
闭环，第三方无需 Runtime Credential 即可重建已发布证据。

## 优先级 4.5——external-tool CLI 真实场景正向提升

**状态：** 下一项工作，尚未证明正向提升。

### 目标与执行顺序

1. 锁定一个变更上下文命令，优先保存会随监控保留周期失效的真实案例、工具响应、
   必要上下文及人工参考判断，形成可重放输入。按事件划分开发集和独立验证集。
2. 固定探针 Agent、模型、Prompt、工具访问与预算。评估根因判断、风险判断和行动建议，
   同时检查事实依据、缺失信息与无依据结论；字段完整率不能代替任务效用。
3. 建立规则与人工参考基线；有定性评分缺口时，引入最小辅助 LLM Judge，再跑基线。
4. 根据开发集失败选择单一干预，例如上下文组织、工具输出、Prompt 或工具使用策略。
   用未参与调优的验证集比较，保持评分政策一致，同时检查回归、有效性与成本。
5. 保存失败分析、改动、比较证据和适用范围；不能因为结果不理想而更换评分口径。

### 最小辅助 Judge 的边界

Judge 是测量工具，执行任务的 Agent 是被测对象。先制定评分标准并用人工标注样本
校准，记录模型、Prompt、评分理由及引用证据，抽查关键分歧。Judge 调用位于外部
工作流，Core 消费已完成且可追溯的评分证据，不获得模型凭据或在线执行职责。
独立验证前冻结评分方式；缺证或 Judge 不可用保持无法判断。Judge 分数上涨必须有
人工抽查或客观任务结果支持，不能单独视为能力提升。此处不要求实现通用 Judge SDK。

### 完成信号与停止条件

至少一次干预在独立验证案例上产生有证据支持的实际改善；提前定义主要指标、回归和
成本约束，报告样本范围、重复运行差异与不确定性。若结果退步或不足以支持改善，
记录有效结论，但正向提升里程碑保持未完成。不要求训练模型或自动优化系统。
复用现有 Profile、Evidence Adapter 与报告；只补这次真实评测必需的缺口。

## 随后——Chora 完成态任务评测最小接入

先选择一类真实任务。Chora 提供完成态结果和证据，Cernora 生成可追溯的评测结论，
Chora 保存并展示通过、失败或无法判断的原因。先证明成功、行为失败、缺证三条路径，
再考虑第二类任务；P4.5 的评分方法按需要复用。运行生命周期、凭据、重试与任务
调度仍归 Chora / 外部工作流。该集成不以完成原 P5–P9 为前提。

## 条件储备：原 P5–P9

以下保留原设计供需求出现时选取，不承诺全部实现，也不要求顺序推进。
P7 是通用 Judge 接口，P8 是其稳定化；P4.5 可先使用范围受限的辅助 Judge。

## 优先级 5——Metric SDK 与 `MetricPlan` Preview

### 目标

等指标覆盖、真实工作流与重复实验暴露出实际复用需求后，再提供收窄的 Preview
接口，让 Profile 组合内置 Metric 与领域自定义 Metric。

### 目标接口

一个小型 `Metric` Interface 负责：

- 稳定的 `metric_id` 与 `metric_version`；
- 参数和输出值 Contract；
- 在适用时从 Authority-bound Evidence 进行确定性评测；
- 每项结果的 Evidence Reference、Validity State 和 Failure Reason。

每个 Profile 通过明确的 `MetricBinding` 声明一个版本化 `MetricPlan`：

```python
MetricPlan(
    metrics=(
        MetricBinding(metric=tool_selection, role="required"),
        MetricBinding(metric=result_grounding, role="required"),
        MetricBinding(metric=answer_completeness, role="advisory"),
        MetricBinding(metric=latency_ms, role="diagnostic"),
        MetricBinding(metric=MyDomainMetric(...), role="advisory"),
    )
)
```

如果 Metric 的 Value Contract 支持，Binding 可以包含版本化 Parameter、
Threshold 与 Report Priority。第一版不提供任意加权总分，避免平均值掩盖关键
Observation 的失败。

第一版 Role 保持收窄：`required` 可以影响 `GateDecision`，`advisory` 会突出展示
但不阻断，`diagnostic` 只用于分析和比较。

Profile 与 Scorer Authority 绑定完整 Plan，包括每个 Metric Version、Role、
Parameter 和 Threshold。改变其中任何一项都要求升级 Authority Version。CLI
调用者不能针对某次 Run 重写 Plan，也不能关闭 Required Observation。

Cernora 将暴露刻意收窄的内置 Metric Library 与 Conformance Fixture。Profile
作者可以导入这些 Module，也可以通过同一个 Interface 实现自定义 Metric。系统
不会提供全局注册中心、自动发现或 Metric Marketplace。

API 从 Preview 开始。现有的 Profile-owned 实现继续有效，直到迁移证据证明共享
接口已经足以替代它们。

### Authoring 与 Conformance

内置和自定义 Metric 使用完全相同的 Contract。Conformance Suite 至少验证：

- 相同 Authority-bound Evidence 重复执行得到相同结果；
- 返回值满足声明的 Value Type、Unit、Direction 与 Validity Contract；
- 所有结论引用存在且位于当前 Evaluation 的 Evidence；
- Missing、Invalid、Contradictory 与 Unsupported Input 不会抛弃 Failure Reason
  或变成通过；
- 自定义 Metric 不能访问未声明网络、凭证或仓库根资源；
- Required Metric 异常 Fail Closed，Advisory/Diagnostic 异常保留可见但不能修改
  其他 Metric 的结果。

第一版 Authoring Flow 是显式 Python Import：Profile 直接构造 `MetricPlan`，不会
扫描 Entry Point 或用户目录。Cernora 提供小型 Built-in Catalog 文档、一个自定义
Metric 教程和合成 Conformance Fixture，但不承诺全局 Name Resolution。

### 交付切片与迁移

1. 从两个现有 Profile 中找出真正重复的 Observation Contract；
2. 提取最小 `Metric`、`MetricResult`、`MetricBinding` 与 `MetricPlan` Preview；
3. 让一个 Profile 只用内置 Metric，另一个同时使用内置与自定义 Metric；
4. 对 Plan Identity、Parameter、Threshold、Role 和 Priority 做 Authority Binding
   与负向测试；
5. 发布 Profile-owned Observation 到 `MetricPlan` 的迁移说明和兼容窗口；
6. 只有两类真实 Profile 都不需要私有旁路后，才考虑提升成熟度。

### 完成信号

至少两个显著不同的 Profile 能通过同一个 `MetricPlan` 组合内置与自定义 Metric；
Authority 变化可被检测，Conformance Failure 会 Fail Closed，并且这个抽象能在
不削弱 Profile-owned Gate Policy 的前提下消除重复。

## 优先级 6——第二个 Producer 与 Runtime Connector 成熟

### 目标

使用第二个独立 Completed-export Producer 证明运行时中立，并发现哪些 Adapter、
Profile 和 Runtime Connector 模式值得成为长期公共接口。

### 计划内容

- 在提炼 Runtime-facing 公共抽象之前，先接入第二个独立 Producer；
- 根据两个集成共同证明的行为，决定是否需要收窄的公共 Runtime Connector；
- Runtime Connector 即使存在，也只负责产生冻结的完成态导出，不会把凭证、调度、
  Sandbox 或进程所有权移入 Cernora；
- 为终态、Tool Call、Artifact、候选代码和基础设施失败发布 Conformance Fixture；
- 改进 Adapter 诊断与最小可重现失败 Package；
- 为工具工作流、Coding Task 和领域确定性评测增加 Profile 模板；
- 记录 Authoring API 的兼容性与迁移规则；
- 支持可交给外部分析工具的 Import 与结果格式。

### 候选 Connector Contract

若两个实现证明值得抽象，通用 Contract 也只描述“一次 Attempt”，而不是一整个
实验：

```text
FrozenAttemptSpec
    -> Runtime Connector
    -> TerminalState + Runtime-owned Output Location + Infrastructure Receipt
    -> Completed Exporter
    -> immutable completed-export directory
```

Harness 继续拥有 Case 展开、并发、Retry 和批量生命周期；Runtime Connector 只把
一个冻结 Attempt 提交给一个具体 Runtime，并等待明确终态。Completed Exporter
负责把 Runtime-specific Output 转成封闭目录；Evidence Adapter 再把该目录解释为
Cernora EvidenceBundle。三层不得合并成一个既运行、又选择证据、又宣布通过的
对象。

第二个 Producer 的验收矩阵必须同时覆盖成功终态、行为失败、超时、中断、部分
Artifact、重复 Tool Event 和 Corrupt Export，并证明同类输入经两个 Producer
得到相同的 Cernora Validity 与 Gate 语义。若两个 Connector 只有表面相似，公共
抽象停止，继续保留两个具体 Companion Integration。

### 完成信号

至少两个独立 Producer 无需在 Core 中加入产品特定分支，就能获得相同评测语义，
并通过同一套公共 Conformance Suite。只有证据支持真正收窄的接口时，才增加
通用 Runtime Connector。

## 优先级 7——可选 LLM-as-a-Judge Preview

`LLM-as-a-Judge` 是一种评测方法；`Preview` 是它在 Cernora 中第一个接口的
成熟度与兼容性标记，不是另一种 Judge。

### 目标

评测确定性程序无法可靠判断的质量维度，同时不让模型可用性或未经验证的模型
意见成为硬事实来源。

### 计划内容

- 通过明确的 Judge Runner 在确定性 Core 之外运行模型；
- 通过 Profile Authority 绑定显式 Judge Definition，包括 Identity、Version、
  Engine、Workflow Stage、Visibility 与 Input/Output Schema Metadata；
- 针对 Problem Discovery、Solution Repair 等不同任务使用 Stage-specific Judge
  Recipe，而不是一个通用 Rubric；
- 冻结 Judge Receipt，绑定 Rubric、Prompt、模型、参数、输入、输出、时延、
  Token、成本与失败状态；
- 每个维度都要求结构化判断和 Evidence Reference；
- 将 Checklist-style Rubric 拆成单独报告的维度；空 Checklist 或不适用 Checklist
  必须判为 Invalid/Inconclusive，不能判为 Pass；
- Structured Parsing 只允许有上限的 Retry，并把每次 Attempt 写入冻结 Receipt；
- 通过 Metric/Report 模型表示 Judge Result，但不削弱确定性检查；
- 将 Transport Error、拒答、超时、结构无效和 Provenance 缺失判为
  `inconclusive`；
- 建立版本化人工标注 Calibration Set 与 Holdout Set；
- 测量一致率、False Pass、False Fail、重复稳定性和已知对抗偏差；
- Preview 默认保持可选、Advisory/Shadow；破坏性变化必须提供 Migration Note；
- Judge Definition 由 Profile 显式选择，不增加自动发现、全局 Scorer Registry
  或硬编码的内部 Model Client。

### Preview Contract 与交付切片

Judge Runner 接收冻结的 `JudgeDefinition` 与输入摘要，返回不可变
`JudgeReceipt`；Cernora 只验证和消费 Receipt，不持有 Provider 凭证，也不在离线
重放时再次调用模型。Receipt 的每个 Attempt 都保留原始结构化输出摘要、Parse
结果、错误类别与成本计量。

1. **Shadow Tracer：** 一个确定性规则无法可靠判断的公开维度、一个版本化
   Rubric 和一份可检查 Receipt；结果不进入硬 Gate。
2. **Failure Matrix：** Transport、Timeout、Refusal、Invalid Structure、Empty
   Checklist、Missing Provenance 与 Contradictory Evidence 全部得到明确
   `inconclusive`。
3. **Calibration Pack：** 人工标签、标注说明、分歧处理、Holdout Split 和公开的
   Agreement/False-pass/False-fail 计算方法。
4. **Profile Binding：** Judge Definition、Stage、Visibility 与 Receipt Schema
   全部进入 Authority；CLI 不能临时换 Rubric 或模型后仍声称同一评测。
5. **Advisory Report：** Judge 与确定性指标并列展示，保留冲突，不用一个总分
   掩盖两者差异。

### 完成信号

用户可以重现和检查冻结的 Judge Receipt，量化它在何时可信，并证明 Judge
故障不能创建通过的 Hard Gate。

## 优先级 8——LLM-as-a-Judge 稳定化

只有 Preview 填补了真实定性缺口，才会开始本阶段。稳定 LLM-as-a-Judge 是
稳定其公共 Contract、失败语义和校准流程，不是让模型输出变成确定性结果。

### 成熟度路径

```text
私有实验 -> Preview -> Supported Preview -> Stable
```

- **Preview：** 可选、Advisory、允许演进，并提供 Migration Note。
- **Supported Preview：** 在明确 Release Line 内支持 Receipt 与 Scorer
  Interface，但校准范围仍然有限。
- **Stable：** Compatibility、Receipt Validation、失败语义、Migration 与
  Recalibration Rule 成为受维护的公共 Contract。

### 升级 Gate

升级需要：

- 至少一个无法由确定性检查替代的公开定性用例；
- 版本化人工标注 Calibration Set 与 Holdout Set；
- 公开的一致率、False Pass、False Fail 和重复稳定性目标；
- 覆盖 Rubric、Prompt 与模型修订的 Drift Check；
- 在适用时覆盖 Prompt Injection、无关冗长、位置偏差和自我偏好；
- 冻结的 Receipt Schema、严格 Provenance 和 Migration Test；
- Transport、拒答、超时、结构无效和 Provenance 缺失全部 Fail Closed；
- 有文档的重新校准触发条件与 Rollback 路径；
- 冻结共享 Stable Interface 前，至少有两个真实 Profile 或集成提供证据。

每次 Rubric、Prompt Template、模型系列或采样策略变化都生成新的 Calibration
Candidate。若 Holdout 指标低于已声明目标、漂移无法解释或某类 Failure 无法可靠
归类，则保持 Preview 或回滚；不会通过放宽 Failure Semantics 来升级成熟度。

Stable 交付物包括 Judge Definition/Receipt Schema、Validator、Calibration Report
格式、Drift Report、Migration Guide 与 Recalibration Runbook。Stable 只承诺这些
Contract 和失败语义，不承诺第三方模型永远输出相同文本或分数。

### Hard Gate 规则

即使 Judge Interface 已经 Stable，它默认仍然是 Advisory。只有通过单独版本化的
Gate Policy，明确 False-pass 容忍度、Outage 行为、Monitoring 与外部授权后，
经过校准的 Judge Observation 才能阻断。确定性 Evidence Check 始终负责硬事实。

### 完成信号

独立用户可以生成并验证同一 Receipt Version，知道何时需要重新校准，并且可以
在没有未记录 Contract Break 的情况下升级。

## 优先级 9——分阶段 Gate Consumer 与 Provenance

### 目标

允许外部 CI 与发布系统安全消费 Cernora Decision，同时继续由外部掌握部署权威。

### 计划内容

- 提供 Advisory/Shadow Reference Consumer，只记录决策，不执行阻断；
- 只有 Policy 与 Threshold 冻结、Negative Test、Evaluator Outage 行为、
  Kill-switch Proof 和 Rollback Proof 完成后，才允许 Non-production Blocking；
- 任何 Production Enforcement 都必须先取得外部 Authority Record；
- 将每个被消费的 Decision 绑定到确切 Candidate 或 Artifact Digest；
- 记录 Profile、MetricPlan、Score、Gate Policy 和 GateDecision Version；
- 在消费系统中保留 Kill Switch；
- 研究可选的 Producer 签名证明，但不夸大内容摘要能证明的范围；
- 保持人员、安全和部署审批独立于 Cernora。

### Consumer Contract 与分阶段上线

Reference Consumer 只接受 Strict Reload 后的 GateDecision，并再次核对 Candidate/
Artifact Digest、Profile Authority、Score、Gate Policy 和 Decision Version。它
不得读取未验证的 Producer Reward，也不得在 Decision 缺失时沿用上一次通过。

```text
observe only
    -> shadow comparison
    -> non-production block
    -> externally authorized production enforcement
```

每次晋级都需要独立的 Policy Record 和退出条件。Shadow 阶段测量 Decision 覆盖、
误报与不可用；Non-production 阶段演练 Evaluator Outage、Timeout、Kill Switch、
Rollback 和旧版本兼容；Production 阶段由外部发布系统保存授权、值班与例外流程。
Cernora 只产生和验证 Decision，不提供绕过码或部署按钮。

消费记录至少包含 Decision Digest、目标 Artifact Digest、消费时间、Consumer
Version、执行模式、最终动作、异常原因和使用的 Authority Record。可选签名只能
证明某个主体对字节作出证明，不能把不完整 Evidence 变成可信事实。

### 完成信号

外部系统可以消费严格绑定的 GateDecision，在评测不可用时安全失败，并能关闭
新增 Gate，而不会绕过已有发布控制。

## `1.0` 产品形态

### 完整系统中的位置

一个完整的 Agent Evaluation System 可以由 Dataset、Experiment Harness、Runtime
Connector、Agent Runtime、Completed Exporter、Evidence Adapter、Cernora 和外部
Gate Consumer 组成。它在外形上会具备常见评测系统的运行、重复、报告和准出流程，
但 Cernora 的差异化边界不会消失：Harness 不能替 Evaluator 宣布通过，Runtime
Output 必须先冻结为 Evidence Contract，Validity 与 Behavioral Failure 必须分开，
持久化结果必须能够 Strict Reload。

因此 Cernora 在 `0.1` 和 `1.0` 都是 Evaluation Core/Harness Component，而不是
Experiment Harness 本身。完整体验通过公开 Companion Workflow 组合；Core 不会为
追求“一站式”而吸收 Runtime、Dataset Scheduler、托管 Trace 或部署权威。

`1.0` 是稳定的离线评测产品，不是 Experiment Harness 或通用 Runtime。它包含：

- Stable 的 Completed-export 链路：EvidenceBundle v2、Canonical Import、
  Evidence、Score 与 GateDecision；
- Stable 的 Fail-closed Validation、Authority Binding、Persistence 与 Strict
  Reload；
- Stable Evidence Adapter Contract，把完成态原生导出转换为 EvidenceBundle v2；
- Stable、Wheel-only 的 Profile Authoring 与 Conformance Workflow，从私有
  Scaffold 一直到 Strict Reload 的 pass/fail/inconclusive 验收；
- Stable 的 Profile-selected 确定性指标 Contract，包括经真实 Profile 验证的
  内置/自定义 Metric 与 `MetricPlan` Surface；
- 可移植的单 Run 与 Batch Result 格式，分别保留 Validity、Behavioral Success、
  Reliability、Safety 与 Efficiency；
- 至少一条完全公开的真实 Reference Evaluation Workflow，其中包含外部 Harness
  与具体 Runtime Connector；同时还要有至少两个独立 Completed-export Producer
  的 Conformance Evidence；
- 明确的 Compatibility、Migration、Security 与 Provenance 边界；
- Reference Shadow 与 Non-production Gate Consumer，但不把部署权威交给 Cernora。

以下两项是条件能力，不是 Stable Core 的强制组成：

- 通用 Runtime Connector 只有在两个具体外部集成证明了真正共享的接口后才加入；
  否则具体集成继续作为 Companion Project，`1.0` 仍然不会声称提供通用 Runtime；
- LLM-as-a-Judge 只有通过校准、漂移和失败 Gate 后才成为 Stable，否则继续作为
  Stable Core 之外的可选 Preview。

即使 Cernora Contract 已经 Stable，Production Blocking 也始终需要外部授权。

## `1.0` 准入条件

Cernora 只有满足以下条件后才应宣布 `1.0`：

- 支持的 Wire、CLI、Profile、Evidence Adapter 和 Metric Contract 已经由
  多个独立 Producer 与 Profile 验证；
- Upgrade 与 Migration 行为有文档并通过测试；
- 确定性重放在每个支持的 Python 版本与平台通过；
- Security、Evidence 与 Provenance 声明符合实现真正证明的能力；
- Release Automation、兼容性测试和漏洞响应可以持续运行；
- 扩展接口足够小，能够在安全演进内部实现的同时维护公共承诺；
- 至少一条真实 Reference Evaluation Workflow 可以只依赖公开 Artifact 重现；
- 如果发布通用 Runtime Connector，它必须由两个具体集成证明，并保持在 Cernora
  Core 之外；
- 如果 `1.0` 包含 LLM-as-a-Judge Surface，它已经通过稳定化 Gate；否则继续
  作为 Stable Core 之外的 Preview；
- 分阶段 Gate Consumer 保持 Shadow、Non-production 和外部授权 Production
  语义。

## 明确不做

这份路线图不包含：

- 通用 Agent Runtime 或 Runtime 自动发现；
- 凭证代理、Sandbox 服务或 Workspace Supervisor；
- 托管评测 SaaS、数据库或 Dashboard；
- Profile Marketplace、Metric Marketplace 或 Benchmark Registry；
- 通用模型 Router 或多 Provider 执行平台；
- 部署审批或生产权威；
- 使用 LLM Judge 代替确定性 Evidence Check。

## 如何选择 Roadmap 工作

一个里程碑只有同时具备以下条件才会开始：

1. 一个具体用户或集成需求；
2. 一个边界收窄的输入、输出与职责约定；只有确需发布时才定义公共 Contract；
3. 可机器检查的正向和负向验收；
4. 明确的兼容性分类；
5. 防止投机性平台扩张的停止条件。

提案应当先描述 Completed Export、所需 Evaluation Decision 和 Evidence Boundary，
再引入新的抽象。
