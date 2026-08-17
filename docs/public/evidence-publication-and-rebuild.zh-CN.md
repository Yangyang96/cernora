# 证据发布与重建策略

[English](evidence-publication-and-rebuild.md) | **简体中文**

Cernora 证据可能记录工具输出、路径和 terminal 内容。任何导出在被明确缩减为中立、可复现
的公开材料前，都应视为敏感数据。

## 可以公开的内容

仓库示例和发布 artifact 只能包含满足以下条件的证据：

- 为中立公开 Profile 和合成 Case 全新生成；
- 体积足够小，可以直接评审；
- 不含凭证、个人数据、私有端点和机器相关路径；
- 是说明或测试公开契约所必需的；
- 可以通过文档化的确定性命令重建。

优先提供一个精简 canonical 示例、一份 SHA-256 manifest 和重建命令，不要提交多份等价
运行副本。

## 禁止公开的内容

不要发布：

- 客户、生产或专有导出；
- 凭证、token、cookie、key 或端点配置；
- 用户名、主目录、checkout 路径或机器/进程/环境清单；
- 私有原始 prompt、对话、调试日志或隐藏预期答案；
- 受保护测试 fixture、未公开漏洞细节或无关源码 diff；
- 编排记录、工作计划、评审归档或开发中间证据；
- 未为公开树构建的仓库元数据或旧历史；
- 可以通过确定性重建和摘要替代的大型重复矩阵。

如果周边结构仍会暴露私有系统，只做字段脱敏并不够。应重新编写中立 fixture 并重建证据。

## 公开证据集

每个公开的生成证据集都要记录：

1. Cernora 和 Python 版本；
2. 公开 Profile 和 Case identity；
3. 精确的确定性命令；
4. 预期成员列表和 SHA-256 摘要；
5. 预期 terminal classification；
6. 命令不使用网络、凭证或源码 checkout 资源的确认。

生成输出应写入新目录，重建不能覆盖旧证据。比较 canonical 字节或排序后的
path-to-digest manifest，不比较时间戳和宿主机元数据。

wheel 内置的 evaluation-core 参考重建命令是：

```sh
python -m cernora.examples.offline_workflow ./cernora-offline-example
```

它会生成合成的中立 completed export，将其转换成 EvidenceBundle v2，执行 import 和
evaluation，再严格 reload 持久化结果。请使用新目录；成功时输出 `pass`。该命令不会启动
Agent、运行 sandbox 或捕获 runtime receipt。

## 重建评审

接受重新生成的证据前：

- 在三个独立的干净目录中运行文档命令；
- 比较需要保持一致的 canonical 输出和摘要；
- 损坏一个 bundle 或 artifact，确认 evaluation 无法通过；
- 扫描名称和 payload，排除密钥、个人路径和私有词汇；
- 确认所有文件都是已声明封闭目录树中的普通文件；
- 确认没有读取未声明的仓库文件。

如果输出发生变化，应先记录并移除非确定性字段。不要在结果生成后抹平有语义差异的内容。

## 保证范围

SHA-256 可以检测内容变化并绑定引用字节，但不能证明字节由谁创建、Producer 未被攻陷、
存储不可变、不可否认性或对恶意 Producer 的抵抗能力。Cernora 提供确定性本地评测，不是
attestation 或归档服务。

打包重建只证明从合成 completed export 开始的 evaluation-core 链路。它不能证明外部
Runtime 执行了 sandbox、凭证、workspace、网络、挂载、超时或清理策略。组合式端到端系统
必须在 Runtime Producer 边界验证这些声明，并在 Experiment Harness 边界验证调度和聚合。

发布 artifact 检查与交付步骤见[本地发布检查清单](local-release-checklist.zh-CN.md)。
