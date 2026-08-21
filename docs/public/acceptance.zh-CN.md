# 公开评测内核与 Priority 1 验收

[English](acceptance.md) | **简体中文**

Cernora `0.1.2` 使用原项目 V1/V2 脱敏公开代表，以及 Priority 1
`tool-workflow` 和 `coding-evaluation` 矩阵进行验收。这些任务标签并不表示
EvidenceBundle v1：所有运行都使用 EvidenceBundle v2/import v2；Priority 1 运行还输出
ResultRecord v1 和 EvaluationReport v1。

验收使用仓库外的干净 Python 3.12.12 和 3.13.12 环境。每个环境都安装固定 Python
依赖和构建后的 Cernora wheel，然后在取消 `PYTHONPATH`、禁用用户级 package 的情况下
运行公开重建脚本。脚本会拒绝从源码仓库导入 Cernora，并在评测进程内阻止 Python socket
创建。

## 范围限制

重建从 wheel 内置的合成 completed export 开始。它不启动真实 Agent，不创建或检查
sandbox，不注入凭证、不管理 workspace、不执行 Runtime 网络或挂载策略，也不捕获工具/
进程观察或生成独立可信的 runtime receipt。阻止 socket 只能证明本次 Evaluator 验收保持
离线，不能证明操作系统级 sandbox。

因此，本次结果验证的是 Cernora 内核链路：Adapter、EvidenceBundle v2、Import、Profile
assessment、Score、GateDecision 和严格 reload。它不是完整端到端 Agent 评测系统的验收；
外部 Agent Runtime 和 Experiment Harness 需要单独验收。

## 结果

- 脱敏 V1 workflow：三次 `pass`，canonical 字节完全相同，并严格 reload 持久化结果。
- 脱敏 V2 coding：backend、frontend 和 fail-closed Case 各运行三次，结果字节相同并严格
  reload。
- `tool-workflow`：18 个冻结场景全部符合预期；17 个可接受场景各生成三次字节相同且
  可严格 reload 的结果树，corrupt 场景被拒绝。
- `coding-evaluation`：20 个冻结场景全部符合 2 pass / 8 fail / 9 inconclusive / 1 rejection；
  19 个可接受场景各生成三次字节相同且可严格 reload 的结果树。
- 损坏 artifact、缺失 artifact、Profile 权威不一致和候选路径穿越都在 eligible pass
  前被拒绝。
- 格式正确但行为错误的 coding candidate 保持 evidence eligible，并生成预期的行为
  `fail` GateDecision。
- Python 3.12.12 和 3.13.12 生成字节完全相同的 3,778-file 验收树，SHA-256 为
  `5c9437c125a1e18988196c2c51c09f29f269cb2c60e88aa157f47a2fb191e6d1`；已审阅摘要的
  SHA-256 为 `132f5dd15a7ff0819e59a47a994e705c016bdbd9474d29151e6112a6b7c1d279`。

精简结果见 [acceptance-summary.json](acceptance-summary.json)。仓库不提交生成的 Bundle、
import 和 evaluation 原始目录树：它们可以确定性重建，且体积大于有效评审范围。此次验收
不使用任何私有 V1/V2 任务数据或开发证据。

## 重建

在干净环境中安装 wheel，切换到 checkout 之外的目录，再通过路径运行仓库中的公开脚本：

```sh
env -u PYTHONPATH PYTHONNOUSERSITE=1 \
  python /path/to/cernora/scripts/rebuild_acceptance.py \
  --output ./cernora-public-acceptance
```

命令只有在将 `cernora-public-acceptance/summary.json` 与
`docs/public/acceptance-summary.json` 按字节比较一致后才会输出 `pass`；SHA-256 必须与
上面的值一致。输出目录必须尚不存在。

这是 evaluation-core 正式版本的证据，不是 Agent Runtime/sandbox 证据。
