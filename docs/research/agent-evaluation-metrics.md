# Agent 评测指标：官方文档与代表性 Benchmark 调研

> 调研日期：2026-08-18。仅采用 OpenAI、Anthropic 官方文档，以及论文原文、官方项目或官方仓库。

## 结论先行

主流 Agent 评测的第一指标不是“轨迹是否像参考答案”，而是**任务最终结果（outcome）是否正确**。轨迹指标主要承担三类职责：解释失败、验证不可从终态观察的政策约束、衡量成本。跨任务的成功率、`pass@k`、`pass^k`、攻击成功率等，则是由单次 trial 的原子判定聚合而来，不能替代单次运行记录。

因此，Cernora Priority 1 应把 `task_outcome` 设为首要 Required 指标；把工具选择、参数和轨迹约束定位为诊断或明确的硬约束。仅靠“工具调用正确 + 回答有依据”不能证明任务已经在环境中完成。

## 官方方法论

### OpenAI

OpenAI 将 trace 定义为一次运行中模型调用、工具调用、guardrail 与 handoff 的端到端记录；trace grader 可回答是否选对工具、是否应当 handoff、是否违反指令或安全政策。进入可重复评测后，再通过 dataset 和 eval run 比较版本。[Evaluate agent workflows](https://developers.openai.com/api/docs/guides/agent-evals)

OpenAI 对 tool call 的官方示例明确拆成两个 grader：函数名是否正确、参数是否正确。它还提醒精确字符串比较可能错误惩罚语义等价参数。[Graders](https://developers.openai.com/api/docs/guides/graders)

OpenAI 同时要求用人类标签校准自动评分，不依赖过于通用的指标；LLM judge 应优先做 pairwise、分类或按明确标准评分，并验证其与人类标签的一致性。[Evaluation best practices](https://developers.openai.com/api/docs/guides/evaluation-best-practices)

### Anthropic

Anthropic 明确区分 transcript 与 outcome：Agent 可以声称已经订票，但真正的 outcome 是环境数据库中是否存在预订。其建议优先评估产物和终态，不要要求唯一工具路径，因为有效解法可能有多条。[Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)

Anthropic 的示例组合了 outcome/state check、确定性测试、工具与参数检查、LLM rubric，以及 `n_turns`、`n_toolcalls`、`n_total_tokens`、`time_to_first_token`、`output_tokens_per_sec`、`time_to_last_token`。对模型 grader，则要求与领域专家校准，并允许证据不足时返回 `Unknown`。

## 指标清单与 Cernora 取舍

| 指标原名 | 精确定义 | 来源 | 粒度 | Priority 1 建议 |
|---|---|---|---|---|
| Outcome / state check | trial 结束时，环境中的可验证状态是否满足目标状态；不以 Agent 的自述代替 | Anthropic；[τ-bench](https://arxiv.org/abs/2406.12045) | 单次 run 原子判定 | **加入并置顶**：`task_outcome`，Required。必须引用独立状态或可信 receipt；没有终态证据应为 `unavailable/inconclusive` |
| Task success | 一个 task 的全部成功条件是否满足，通常为 0/1 | [AgentBench](https://github.com/THUDM/AgentBench/blob/main/docs/Introduction_en.md)；WebArena | 单次原子判定；跨 task 平均后成为成功率 | 保留 `task_completion`，但定义为 outcome 判定的 Gate 映射，避免与 `task_outcome` 重复计分 |
| FAIL_TO_PASS | 原先失败、用于验证修复的测试中通过的比例 | [SWE-bench grading code](https://github.com/SWE-bench/SWE-bench/blob/main/swebench/harness/grading.py) | 单次 coding run 原子数值 | `coding-evaluation` 加入：`resolution_test_rate` |
| PASS_TO_PASS | 原先通过的回归测试中仍通过的比例；SWE-bench 仅在 F2P=1 且 P2P=1 时判定 FULL resolved | SWE-bench | 单次 coding run 原子数值 | `coding-evaluation` 加入：`regression_test_rate`，Required 硬约束 |
| Tool/function name correctness | 实际调用的工具名是否与期望工具匹配 | OpenAI Graders | 单次调用/单次 run 原子判定 | 已由 `tool_selection` 覆盖 |
| Tool argument correctness | 调用参数是否满足参考值或语义约束 | OpenAI Graders | 单次调用/单次 run 原子判定 | 已由 `argument_accuracy` 覆盖；应结构化比较，不比较 JSON 字符串表示 |
| Function relevance / irrelevance detection | 有合适工具时是否调用；没有适用工具时是否不调用 | [BFCL 官方说明](https://sky.cs.berkeley.edu/project/berkeley-function-calling-leaderboard/) | 单次 prompt 原子判定 | **加入**：`tool_invocation_decision`，Required；它不同于“在已调用工具中是否选对” |
| Executable accuracy | 实际执行函数并以精确结果、实时数值容差或结构匹配判定调用结果是否正确 | [BFCL evaluation](https://gorilla.cs.berkeley.edu/blogs/8_berkeley_function_calling_leaderboard.html) | 单次调用原子判定；再聚合 accuracy | 映射到 `tool_result_integrity`；仅有生产者自报结果时不能声称 executable accuracy |
| Milestone similarity | 将必须达到的中间状态定义为 DAG；按拓扑约束把 milestones 与轨迹步骤最优匹配，并聚合各 milestone 的状态相似度 | [ToolSandbox](https://github.com/apple/ToolSandbox/blob/main/README.md) | 单次 run 的部分得分 | **加入其思想而非浮点总分**：`required_milestone_coverage`；顺序只表达偏序，不固定唯一轨迹 |
| Guardrail similarity / forbidden state | 受保护状态必须与参考状态相同，否则该 milestone 为 0 | ToolSandbox | 单次 run 原子硬约束 | 已由 `forbidden_action_absent` 部分覆盖；应同时检查副作用后的环境状态，而不只查调用名 |
| Benign task success | 无攻击时是否完成用户任务 | [AgentDojo paper](https://papers.neurips.cc/paper_files/paper/2024/file/97091a5177d8dc64b1da8bf3e1f6fb54-Paper-Datasets_and_Benchmarks_Track.pdf) | 单次安全 case 原子判定 | 基础 `task_outcome` 即可 |
| Safe success under attack | 在攻击存在时，既正确完成用户任务，又没有 adversarial side effects | AgentDojo 的 Utility Under Attack 的单 case 基础判定 | 单次安全 case 原子合取 | **加入语义**：Gate 必须是 outcome 与 policy/safety 的合取，安全失败不可被任务成功抵消 |
| Attack goal achieved | 攻击者目标是否实现，即是否执行恶意动作 | AgentDojo Targeted ASR 的单 case 基础判定 | 单次安全 case 原子判定 | `forbidden_action_absent` 的反面；保留原始 observed value，不只输出总 Gate |
| Turns / tool calls / tokens | 一次 run 的轮数、工具调用数、总 token 数 | Anthropic | 单次 run 原子计数 | 工具调用数现在加入；turn/token 只有导出提供可信值时才记录，否则 `unavailable` |
| Latency metrics | TTFT、输出 token/s、到最后 token 时间 | Anthropic | 单次 run 原子数值 | `latency_ms` 太含糊；建议以后拆为带明确时钟边界的字段。Priority 1 可保留 end-to-end latency，但必须声明计时区间 |
| API requests / token usage | LLM 请求数、输入/输出/总 token 数，以及逐请求 usage | [OpenAI Agents SDK Usage](https://openai.github.io/openai-agents-python/usage/) | 单次 run 原子计数 | 加入可选诊断字段，但不允许从无法验证的文本推断 |
| Infrastructure failure | 评测没有产生有效候选结果，例如 patch 未应用或基础设施失败 | SWE-bench harness | 单次评测有效性状态 | **必须进入 report validity，不是 Agent 失败**；与 `failed` 分离为 `unavailable/inconclusive` |
| Human–grader agreement | 自动 grader 在已有人类 ground truth 的校准集上与专家标签保持一致 | OpenAI；Anthropic | 跨样本 grader 质量指标 | 不属于 Agent ResultRecord；Priority 1 应记录 grader/version/provenance，模型 grader 到 Priority 7 再引入一致性门槛 |

## 跨 trials 聚合指标

| 指标 | 精确定义 | 来源 | Priority 1 建议 |
|---|---|---|---|
| Success rate / resolved rate | 成功 task 数除以总 task 数；每个 task 先有独立的 0/1 outcome | AgentBench、WebArena、SWE-bench | Priority 4 batch reporting；Priority 1 只生产可靠的单次原子判定 |
| `pass@k` | 对每个 task 的 k 次尝试中至少一次成功的概率/估计值 | Anthropic；HumanEval 系列 | Priority 4；适合“多次尝试有一次可用” |
| `pass^k` | 对每个 task 的 k 次 trial 全部成功的概率；强调一致可靠性 | Anthropic；τ-bench | Priority 4，且应作为可靠性的核心聚合指标 |
| Benign Utility | 无攻击时完成用户任务的 task 比例 | AgentDojo | Priority 4 security suite |
| Utility Under Attack | 安全 case 中同时完成用户任务且没有 adversarial side effect 的比例 | AgentDojo | Priority 4；不能与 ASR 合并成模糊总分 |
| Targeted ASR | 安全 case 中攻击者目标被实现的比例 | AgentDojo | Priority 4，方向为越低越好；单次 run 保留 attack-goal 原子判定 |
| Mean/P95 latency、cost | 跨 trials 的耗时或成本分布 | BFCL leaderboard；Anthropic | Priority 4；报告分布，不只给平均数 |
| 95% confidence interval | 聚合指标的不确定性区间 | AgentDojo | Priority 4；用于避免把采样噪声当成版本差异 |

## 对当前 Priority 1 指标集合的修正

### 应作为主指标

1. `task_outcome`：最终环境状态/产物是否满足目标。
2. `policy_compliance`：没有违反不可抵消的安全、权限和业务规则。
3. `evaluation_validity`：证据、grader 与运行基础设施是否足以作出结论；这是报告状态，不是 Agent 能力分。

Gate 语义应接近：`valid evidence AND task_outcome AND policy_compliance`。任何一项缺证据都应是 inconclusive，而不是失败或通过。

### 应加入的过程指标

- `tool_invocation_decision`：应不应该调用工具。
- `required_milestone_coverage`：是否达到所有必要中间状态；允许多条合法轨迹。
- `termination_correctness`：是否在成功、不可恢复失败或需要升级时正确结束。该项在上述来源中不是统一命名指标，但可由终态、步数上限和完成后的额外副作用确定性推导。

### 应降级为诊断或有条件硬约束

- `sequence_adherence` 不应验证唯一黄金路径，只验证由政策或数据依赖产生的偏序。
- `action_relevance_ratio`、`no_progress_loop_absent` 可帮助定位效率问题，但并非主流 benchmark 的顶层成功指标。建议 Advisory，不应把一个有效但不同的方案判失败。
- `tool_selection`、`argument_accuracy` 是重要诊断；只有错误调用本身造成政策违反，或任务契约明确要求该调用时，才直接决定 Gate。
- token、cost、latency 必须保留单位、方向、计时范围和证据来源，不进入任意加权总分。

## 最终建议

Priority 1 不应继续扩成“18 个同等地位的指标”。建议形成三层模型：

1. **Outcome**：`task_outcome`，回答“做成了吗”。
2. **Constraints**：`policy_compliance`、idempotency、forbidden state/action，回答“是否用允许的方式做成”。
3. **Diagnostics**：tool decision/name/arguments、milestone coverage、grounding、termination、recovery、calls/retries/tokens/latency，回答“为什么成功或失败、代价多大”。

这比将所有过程检查并列为 Required 更符合 OpenAI、Anthropic、τ-bench、SWE-bench、AgentDojo、BFCL 和 ToolSandbox 的共同做法，也更能保持 Cernora 的 runtime-neutral 与可复现边界。
