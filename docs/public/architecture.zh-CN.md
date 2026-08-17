# 架构

[English](architecture.md) | **简体中文** | [README](../../README.zh-CN.md) |
[产品路线图](../../ROADMAP.zh-CN.md)

Cernora 是一个确定性 Python Evaluator，用于评测已经完成的 Agent Run。它读取普通本地
文件，输出由 Evaluator 拥有的 Evidence、Score 和 GateDecision，但不负责 Agent 执行。

本文描述 `0.1.x` 已交付的架构。计划中的指标、报告、Runtime Connector 和 Gate Consumer
属于产品路线图，不是当前契约。

## 完整系统构成

Cernora 是组合式评测系统中的独立决策内核：

```text
Experiment Harness
  -> External Agent Runtime
       -> completed export + runtime-owned receipt
  -> Cernora
       -> Evidence + Score + GateDecision
  -> aggregate report
```

外部 Agent Runtime 负责 Agent workflow 执行、凭证、sandbox、workspace、网络和挂载
策略、资源限制、超时、终止、证据捕获和清理。Cernora 不实现或代理这些职责。

Experiment Harness 负责任务矩阵、调度、重复运行、基础设施重试策略、聚合和报告。它必须
原样保留每个 Cernora GateDecision，不能把 Runtime 成功、reward 或任务完成直接转换成
评测 `pass`。

这种分工让执行权和裁决权相互独立。完整端到端系统需要组合三个角色；单独安装 Cernora
只会得到评测内核和 completed-export 接口。

## 数据流

```text
producer-owned completed export
  -> explicit offline Adapter
  -> EvidenceBundle v2 plus declared artifacts
  -> canonical import and strict reload
  -> explicitly selected Profile
  -> Evidence v1 and Score v1
  -> evaluator-composed GateDecision v1
  -> atomic persistence and strict result reload
```

Producer 决定如何运行 Agent 并导出终态事实。Adapter 只负责规范化完成态导出。之后的
验证、权威绑定、评测和结果发布由 Cernora 负责。

## 组件职责

### Adapter

Adapter 读取一个完成态本地导出，写入封闭、canonical 的 EvidenceBundle v2 目录树。它
不启动、恢复或重试进程，不获取凭证、不访问网络，也不评分。调用方必须显式选择 Adapter。

详见 [Adapter conformance](adapter-conformance.zh-CN.md)。

### Importer

Importer 严格解析 EvidenceBundle v2，校验摘要和 artifact 字节，把内容绑定到给定的
Profile 与 Case 权威，然后发布 canonical import package。未知字段、不支持的版本、不安全
路径、缺失 artifact、摘要不一致和身份冲突都会被拒绝。

Import 发布具有冲突保护：完全相同的重复操作按字节幂等，不同结果不能覆盖已有输出。严格
reload 会重新检查落盘后的封闭 package，不信任内存中的对象。

### Profile

Profile 拥有一个 `CaseProfile` 权威、Profile 特定的 import validation 和确定性 assessment。
Assessment 返回绑定后的 Evidence、Score 和必选观察集合，但不持久化结果，也不组合
GateDecision。

Profile 通过内置 ID 或本地路径显式选择，不扫描、不使用 entry-point discovery，也没有
注册中心。本地 Profile Python 是受信任代码，以当前用户权限执行，不受 sandbox 保护。

详见 [Profile 编写](profile-authoring.zh-CN.md)。

### Deep evaluator

Evaluator 重新加载已导入内容、绑定当前权威、生成确定性 evaluation identity、调用 Profile、
交叉检查返回的 Evidence 和 Score，再根据 Profile Gate Policy 组合 GateDecision。结果会
写入封闭 package，并在接受前严格 reload。

行为失败与证据缺失或无效始终分开。基础设施、完整性或权威存在不确定性时，不能得到
`pass`。

## 公开契约

Cernora `0.1.x` 只接受：

- `agent.evaluator.evidence-bundle/v2` bundle wire；
- canonical import package 使用的 v2 receipt 和 manifest；
- 已公开说明的 imported-evaluation package 契约。

Evaluator 输出并保留：

- `agent.evaluator.evidence/v1`；
- `agent.evaluator.score/v1`；
- `agent.evaluator.gate-decision/v1`。

`agent.evaluator.*` 是协议 ID，不是 Python 包名。Bundle 或 import v1 不会被接受、转换或
静默升级。

## 完整性与权威

Identity 会绑定 Producer、Run、Profile、Case、fixture 和 artifact。Canonical JSON 与
SHA-256 摘要可以检测内容变化，但不能证明 Producer 身份、不可否认性、历史不可变或
Producer 未受攻击。

Cernora 只验证 EvidenceBundle v2 中的 receipt 字段和已声明 artifact 字节。它不生成或
认证外部 Runtime attestation，也无法证明 sandbox 已创建、隔离策略已执行，或观察是在
Agent 控制范围外捕获的。这些声明需要可信的外部 Runtime Producer 及其 conformance 和
安全证据。

Cernora 只打开已声明的普通文件，拒绝封闭输出树中的符号链接，也不会原地修复持久化证据。
这些控制用于保护确定性本地评测，不会把 Cernora 变成 Runtime sandbox 或证据仓库。

## 扩展边界

Profile 和 Adapter 协议是有边界的 Preview 扩展点。Cernora 不提供插件市场、注册中心、
托管 Scorer、Workflow Engine 或通用 Runtime。[兼容性矩阵](compatibility-matrix.zh-CN.md)
说明哪些接口在 `0.1.x` 内稳定。未来 Metric SDK 和 Runtime Connector 的顺序与验收条件见
[产品路线图](../../ROADMAP.zh-CN.md)，它们不是当前扩展契约。
