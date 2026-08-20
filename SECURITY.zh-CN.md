# 安全策略

[English](SECURITY.md) | **简体中文**

## 支持版本

Cernora `0.1.1` 是当前版本。安全修复只针对最新发布的 `0.1.x`，不承诺长期支持周期。

## 报告漏洞

不要在公开 Issue、Discussion 或 Pull Request 中披露尚未修复的漏洞。

请使用 [GitHub 私密漏洞报告](https://github.com/Yangyang96/cernora/security/advisories/new)。
如果页面没有显示私密报告表单，请通过 GitHub 联系当前维护者建立私密渠道，但不要在
首次请求中附带利用细节。本项目不虚构邮箱、响应时限或站外报告地址。

在安全的前提下，请提供：

- 受影响的版本或 commit；
- 相关命令或公开 API；
- 使用合成数据的最小复现；
- 预期与实际的 fail-closed 行为；
- 潜在影响和已知缓解措施。

移除凭证、个人路径、私有导出和生产数据。维护者会通过私密渠道协调验证和披露。响应和
修复时间取决于贡献者的可用时间，不作保证。

## 安全边界

Cernora 评测已经完成的普通文件导出。它不启动或监督 Agent，也不声称能 sandbox
代码。通过 `--profile-path` 选择的本地 Profile 是受信任 Python，会以调用用户的权限
执行；运行前请检查代码。

Agent 启动、凭证、workspace、网络或挂载隔离、资源限制、超时和清理属于外部 Agent
Runtime。Cernora 只验证 EvidenceBundle v2 中的 receipt 字段和已声明 artifact 字节。
完整性摘要不能证明声明的隔离真实发生，也不能证明观察是在 Agent 控制范围外捕获的。

格式错误、损坏、权威不一致或不完整的证据都应视为不可信输入。Cernora 会拒绝这些输入
或 fail closed，但内容摘要不能证明 Producer 身份、不可否认性，也不能抵抗已被攻陷的
Producer。

不要在 EvidenceBundle、Profile 资源、示例或报告中放入密钥。密钥一旦泄漏，应先在签发
系统中撤销，再准备脱敏复现。
