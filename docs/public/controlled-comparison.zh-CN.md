# 受控比较

Cernora `0.1.4` 新增增量 Preview surface，用于从一个完整 `BatchInput v1` 中比较恰好两个
Configuration。它只消费已完成证据，不运行 Agent、不选择 Configuration，也不授权晋级。

## 受控输入

`ComparisonInput v1` 内嵌完整 Batch Input，并选择 Baseline 与 Candidate。输入必须穷尽 Batch
中的 Configuration，并绑定每个 Case、split、Experiment 和 repetition。每个
Case×Configuration cell 都内嵌严格 canonical `ExperimentAuthority v1`；Core 重算出的摘要必须
等于 Batch slot 的 `experiment_id`。Runtime、model、prompt/instruction、tool schema、generation
configuration、timeout、resources、retry policy、dataset、Profile、case-neutral evaluation
policy、case-specific evaluation authority、report contract 与 statistical plan projection 都由
该绑定 authority 派生，不是彼此独立的调用方声明。

独立内容寻址的 `Treatment v1` 声明全部允许差异。封闭 change kind 包括 prompt/instruction、
model、tool schema、generation configuration 和 Runtime version。每个实际 projection 差异都必须
恰好对应一个 Treatment entry；不变量或未声明差异只能得到 `not_comparable`，不能产生部分比较。
Configuration-level projection 还必须跨 Case 一致；存在 Evaluation receipt 时，其 Case、Profile
与 evaluation authority 必须匹配 projection。
调用方不能提交 rate、delta、interval 或 conclusion。

## 统计

首个 Primary Outcome 是 Reliable Success Rate：仅 `pass` 计一；行为失败、评测无效和基础设施
不可用均计零。它的预声明 scope 可以是全部 Case，也可以是一个精确、已声明的 `split_id`；rate、
delta 与 clustered interval 只使用该 scope 中的 Case。Trial 按 Case 与预声明 repetition 配对；
重试 Attempt 只作诊断，不能成为独立样本。

`case-clustered-paired-bootstrap/v1` 使用版本化 SHA-256 counter sampler 对完整配对 Case 抽样，
保留所抽 Case 的全部 Trial，固定 10,000 次 resample，并报告封闭 95% nearest-rank percentile
区间。seed 来自 Comparison Input 身份。区间触及零即为 `uncertain`；不输出 p-value 或显著性声明。

预声明且合格时，pass@k 为 `1-C(n-c,k)/C(n,k)`，pass^k 为 `C(c,k)/C(n,k)`。计算要求相等的
独立 Trial 数；retry 不计入。

## Guardrail 与结论

Hard Guardrail 必须预声明、明确 scope，并分别评估。支持 evaluation validity、Reliable Success
Rate 和 Profile-owned failure-code rate。证据缺失或不兼容会使 Guardrail unavailable，并阻止
`improved`。

封闭结论为 `improved`、`no_change`、`uncertain`、`mixed`、`regressed` 和
`not_comparable`。只有 Primary 区间整体为正、点估计达到预声明 practical threshold、且所有 hard
Guardrail 都满足时才能 `improved`。Guardrail 不会被平均进 composite。Summary 还报告配对四乘四
outcome transition matrix 和证据绑定的 failure-code migration；这些诊断不选择结论。

## API、package 与 CLI

包根 Preview 函数包括 `materialize_treatment`、`materialize_comparison_input`、
`build_comparison_summary`、`summarize_comparison`、`reload_comparison_summary` 和
`reload_comparison_package`。`reload_batch_summary_package` 以无路径的 `BatchInput` 加派生
`BatchSummary` 暴露完整严格 M2 package，避免 assembler 丢失 Trial 证据。

```bash
cernora comparison validate comparison-input.json
cernora comparison summarize comparison-input.json --output comparison-summary
```

输出是新的原子封闭目录，包含 canonical input/Summary JSON、确定性 Markdown、绑定 receipt 与
`digests.json`。有效比较即使是 `not_comparable` 或未改进也返回 `0`；用法/配置冲突返回 `2`；
损坏或不可验证输入返回 `3`。

## 兼容与迁移

M3 surface 是本地 `0.1.4` release candidate 的增量 Preview，尚未公开发布。现有 evidence、
Profile、evaluation 和 M2 Batch 契约不变；M2 调用方无需迁移。新的 Comparison producer 必须固定
版本化 schema，并在所有声明与 Trial 证据冻结后才生成内容身份。

现有 Comparison producer 可以继续把 `primary_outcome.scope` 写为 `all`；其 canonical object
仍只有原来的字段与字节，不能包含 `split_id`。选择 `scope: "split"` 时，producer 必须同时提供
一个已经由 Comparison Case 使用的 `split_id`。未知 split、没有 ID 的 `split`，以及携带 ID 的
`all` 都无效。该选择只改变 Primary 统计与由此得到的结论；Guardrail 保留各自 scope，pass@k、
outcome transition 与 failure migration 仍是整个 Comparison 的诊断。
