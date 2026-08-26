# Validity-first 批次摘要

Cernora `0.1.3` 新增一个增量 Preview surface，用于对已经完成的实验矩阵生成确定性摘要。
Core 仍然与 Runtime 无关：它不会启动、认证、调度、重试、中断或清理 Agent，也不会解析
Companion Execution Pack。

## 权威输入

`BatchInput v1` 是单个 canonical、内容寻址 JSON。producer 必须声明完整、有序的 Trial
slot 清单，并为每个 slot 提供且只提供一个已完成 Trial。每个 Trial 绑定 RunPlan、
Execution、Case、Configuration、repetition、Experiment 与完整 Attempt chain。

每个 Attempt 必须且只能包含以下一种事实：

- 以逐字节 base64 文件嵌入的完整 Evaluation Package；Core 严格检查 evaluator manifest、
  payload digest、版本化契约和跨契约身份；或
- 对未产生可评估 export 的 Attempt，提供规范化、receipt 绑定的 lifecycle failure。

P4 Attempt identity 与 source producer Attempt identity 明确分离：前者保持 Execution 全局
retry chain，后者要求嵌入的 Evaluation Package 精确绑定它实际评估的 producer Attempt。

Core 拒绝未知字段、非 canonical JSON、调用方提供的 rate、裸 pass/fail JSON、不完整、
重复或未知 Trial、断裂 retry predecessor、RunPlan/Execution 绑定不一致、digest 篡改、
非法 package 文件、未完成 Execution 和预算耗尽。经验证的 lifecycle failure 会作为
unavailable Trial 保留，不会使整个 batch 无效。

## Outcome 与 rate

Core 只派生四种 Trial outcome：`pass`、`behavioral_fail`、`evaluation_invalid` 和
`infrastructure_unavailable`。planned Trial 始终是分母权威。整体、Configuration、Case
和 Case×Configuration 分组均报告精确分子/分母：

- Evaluation Validity Rate = pass 加 behavioral fail / planned Trials；
- Behavioral Success Rate = pass / valid Trials；
- Reliable Success Rate = pass / planned Trials。

当分组没有 valid Trial 时，Behavioral Success Rate 表示为 `0/0` 和 null，而不是零。
Attempt 诊断保留首次成功、retry 数量/比率、Attempt evaluation validity、基础设施分布与
已验证资源总量。任一 Attempt 缺少所需结构化 receipt 时，总量为 unavailable；缺失 token
或 cost evidence 永远不会被写成零。

Milestone 2 不发布 delta、置信区间、bootstrap、pass-at-k、Winner、improvement 或
regression 结论。Profile failure code 只能来自严格加载的版本化 ResultRecord，不能从自由
文本猜测。

## Python 与 CLI

包根 Preview 函数包括 `validate_batch_input`、`build_batch_summary`、`summarize_batch` 和
`reload_batch_summary`。发布函数原子写入一个全新封闭目录，并拒绝覆盖任何现有路径。
package 保留 `batch-input.json`，使 strict reload 能重新派生 Summary。`batch-summary.json`
是权威表示；`batch-summary.md` 只能表达相同事实，`digests.json` 封闭整个 package。

```sh
cernora batch validate batch-input.json
cernora batch summarize batch-input.json --output batch-summary
```

退出码 `0` 表示输入或 Summary 有效，即使所有行为 Trial 都失败；`2` 表示 CLI 使用或
authority 选择不兼容；`3` 表示输入损坏、不完整或不可验证。Batch 质量不使用退出码 `1`，
也不是 deployment Gate。

## 迁移说明

这是增量、显式启用的 Preview surface。现有 evidence import、evaluation、Profile 和 Gate
调用方无需迁移。新的 batch producer 必须固定 `agent.evaluator.batch-input/v1`，使用 wheel
内的 `batch-input-v1.schema.json`，在所有 Trial/Attempt 事实冻结后生成内容身份；之后任何
变化都必须产生新的 Batch Input identity。
