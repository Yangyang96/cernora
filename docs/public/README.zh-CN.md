# Cernora 文档

[English](README.md) | **简体中文**

- [架构](architecture.zh-CN.md)：完整系统构成、Evaluator 边界、数据流和权威。
- [产品路线图](../../ROADMAP.zh-CN.md)：按结果排序的演进计划，不接管 Agent Runtime 或
  Experiment Harness。
- [Profile 编写](profile-authoring.zh-CN.md)：创建、实现和验证本地 Profile。
- [Adapter conformance](adapter-conformance.zh-CN.md)：把完成态导出规范化为封闭的
  EvidenceBundle v2 目录树。
- [证据发布与重建](evidence-publication-and-rebuild.zh-CN.md)：哪些证据可以公开，以及如何
  重建生成证据。
- [公开 V1/V2 代表性验收](acceptance.zh-CN.md)：合成 completed export 重放、对抗矩阵、
  范围限制和重建命令。
- [兼容性矩阵](compatibility-matrix.zh-CN.md)：`0.1.x` 稳定层级和版本化契约。
- [本地发布检查清单](local-release-checklist.zh-CN.md)：发布候选交付前的源码、artifact 和
  wheel-only 检查。
- [正式发布流程](release-day-runbook.zh-CN.md)：仓库设置、不可变发布操作、Trusted
  Publishing 和发布后验证。

发布维护者在发布前运行 `uv run python scripts/release.py preflight`，生产发布后运行
`uv run python scripts/release.py verify --version <version>`。

安装方式和可运行离线示例见项目[中文 README](../../README.zh-CN.md)。
