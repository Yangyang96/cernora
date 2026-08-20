# 变更记录

[English](CHANGELOG.md) | **简体中文**

Cernora 的重要变化记录在这里。项目遵循语义化版本；1.0 之前的兼容性还受公开兼容层级
约束。

## Unreleased

## 0.1.1 - 2026-08-20

### Added

- 新增 Preview `ResultRecord` v1、`EvaluationReport` v1、公开 schema，以及针对显式选择
  structured result 的 Profile 的 manifest 绑定严格持久化。
- 新增独立版本化的 `builtin:tool-workflow` Profile，并提供冻结的 18 Case 合成
  验收矩阵，覆盖 pass、行为 fail、inconclusive 和损坏输入拒绝。
- 新增独立版本化的 `builtin:coding-evaluation` Profile，覆盖 Candidate Tree v1
  重建、Profile-owned 冻结执行 capsule、F2P/P2P 诊断、派生 diff/篡改策略和 20 行确定性
  验收矩阵；原有 `builtin:coding-task` Profile 保持不变。
- 为发布维护者提供完整本地 preflight 命令，以及生产 PyPI artifact、干净安装和
  Python 3.12/3.13 验收流程验证命令。

### Changed

- `ProfileAssessment` 新增可选字段 `result_records=()`。现有 Profile 保持原有
  Score/Gate 行为；只有显式提供 records 的 Profile 才会生成 evaluation report。
- CI、artifact 检查、Trusted Publishing 和发布流程现在从声明版本推导 artifact 名称，
  不再硬编码 `0.1.0`。

## 0.1.0 - 2026-08-14

首次公开发布。

### Added

- 通过 EvidenceBundle v2、canonical import 和严格 reload 对完成态导出进行离线评测。
- 由 Evaluator 生成 Evidence v1、Score v1 和 GateDecision v1，并采用 fail-closed 结果。
- 显式内置 `offline-workflow` 和 `coding-task` Profile。
- Preview Profile/Adapter 编写协议和 conformance helper。
- 默认私有的项目本地 Profile scaffold，以及显式、受信任的本地加载。
- wheel 内置 workflow 和 coding 示例，无需仓库资源即可完成 adapt、import、evaluate 和
  严格结果 reload。
- 脱敏的 V1/V2 代表性验收重建：三次确定性运行，并覆盖损坏、缺失、权威不一致和路径
  穿越的 fail-closed 检查。
- Apache-2.0 治理、兼容性、证据发布和本地发布指南。

### Documentation

- 明确 Cernora 是组合系统中的独立评测内核。打包示例从合成 completed export 开始，
  不声称已经验收 Agent Runtime、sandbox、runtime receipt 捕获或 Experiment Harness。

### Changed

- 最终候选验收后没有修改产品代码或 wire contract；发布日改动仅限发布元数据和文档。

### Compatibility

- Python 3.12 和 3.13 是支持的语言版本；操作系统支持范围更窄，以原生证据矩阵为准。
- EvidenceBundle v2 和 import v2 是唯一接受的公开输入格式。
- Supported Preview 接口在 `0.1.x` 内保持兼容；编写 API 属于 Preview，可以随
  changelog 和迁移说明演进。
