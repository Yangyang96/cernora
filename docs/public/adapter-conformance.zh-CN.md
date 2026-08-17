# Adapter conformance

[English](adapter-conformance.md) | **简体中文**

Adapter 把一个已经结束的普通文件导出转换成 EvidenceBundle v2 及其声明的 artifact。
它是纯规范化接口，不是 Agent Runner。

## 协议

```python
from pathlib import Path

from cernora import AdaptedBundle, CompletedExport


class MyAdapter:
    def adapt(self, completed_export: CompletedExport, output: Path) -> AdaptedBundle:
        # 读取并验证 completed_export.root，然后原子创建 output。
        # canonical bundle 必须位于 output / "bundle.json"。
        ...
```

调用方提供 completed-export 根目录和尚不存在的输出路径。符合协议的 Adapter 返回
`AdaptedBundle(bundle_path=output / "bundle.json")`。

## 输出要求

输出目录必须是封闭目录：只包含 `bundle.json` 和 bundle 声明的所有 artifact 路径，
不能有额外文件。具体要求如下：

- `bundle.json` 是 `agent.evaluator.evidence-bundle/v2` 的严格 canonical JSON；
- 所有文件都是普通文件，任何路径都不能是符号链接；
- artifact 路径安全、相对，且位于输出目录内；
- 每个 artifact 的字节内容都与其 SHA-256 摘要一致；
- terminal answer 内容与其拥有的 artifact 字节一致；
- Profile、Case、fixture、Producer 和 Run identity 来自 completed export 或显式 Adapter
  配置，不能由 Evaluator 在运行结束后根据预期结果编造。

先写入私有 staging 目录，再以不替换现有输出的方式发布。失败时不能留下部分已接受目录。
等价的 completed export 应生成字节完全相同的输出。

## 禁止行为

Adapter 不能：

- 启动、恢复、重试、终止或清理 Agent；
- 获取或转发凭证；
- 访问网络服务；
- 推断缺失的 stdout、stderr、delivery、commit 或 terminal 事实；
- 把预期答案当作已观察证据；
- 对行为评分或组合 GateDecision；
- 把其他 bundle 版本静默转换成 v2。

如果 completed export 无法证明必需事实，应拒绝它，或按 v2 契约如实表示 terminal 状态。
不要制造成功历史。

## 运行 conformance helper

```python
from pathlib import Path

from cernora import CompletedExport, check_adapter_conformance

summary = check_adapter_conformance(
    MyAdapter(),
    CompletedExport(root=Path("completed-export")),
    Path("conformance-output"),
)
print(summary.bundle_sha256)
```

`conformance-output` 必须尚不存在。Helper 会运行 Adapter，检查封闭目录树、严格 bundle、
canonical 字节和 artifact 摘要，并返回 identity 摘要。Preview conformance 检查把单个输出
文件限制为 16 MB。

Helper 不监控网络或进程创建。请在 Adapter 自身测试中执行这些策略，并始终针对目标
Profile 完成真实 import 和 evaluation。

## 验收矩阵

至少测试：

1. 有效 completed export 的 adapt、import、evaluate 和严格 reload；
2. 三次等价运行生成相同 bundle 与 artifact 字节；
3. 缺失、额外、被修改和符号链接输入；
4. 格式错误的 terminal status、process result 与 receipt 组合；
5. 错误的 Profile、Case、fixture、Producer 和 Run identity；
6. 截断、非法 UTF-8 和摘要不一致的 artifact；
7. 已存在的输出路径，且绝不能覆盖或修复。

Conformance 只验证格式和完整性，不能证明已被攻陷的 Producer 说了真话。提交 Adapter
fixture 或生成 bundle 前，请阅读[证据发布与重建策略](evidence-publication-and-rebuild.zh-CN.md)。

Adapter conformance 也不能证明 Agent 在 sandbox 中运行，或 runtime receipt 是在 Agent
控制范围外捕获的。这些属于外部 Agent Runtime 声明。Cernora 只验证边界处收到的完成态
字节和已声明权威；Runtime 及其 Experiment Harness 需要单独的 conformance 和验收。
