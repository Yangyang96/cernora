# Profile 编写

[English](profile-authoring.md) | **简体中文**

Profile SDK Preview 允许项目针对一种明确的 completed evidence 定义确定性 validation 和
assessment。它不提供 Runtime 执行或插件发现。

## 创建私有 scaffold

在项目目录中运行：

```sh
cernora profile init my-profile
```

Cernora 使用最近的 Git 根目录；如果不存在 Git 根目录，则使用当前目录。命令会创建：

```text
.cernora/
  .gitignore
  profiles/
    my-profile/
      profile.py
      profile.json
      resources/
        expected-value.json
      cases/
        pass.json
        fail.json
        inconclusive.json
        corrupt-artifact.json
        authority-mismatch.json
        scorer-policy-mismatch.json
        gate-policy-mismatch.json
      fixtures/
        pass/
        fail/
        inconclusive/
        corrupt-artifact/
        authority-mismatch/
        scorer-policy-mismatch/
        gate-policy-mismatch/
      tests/
        test_profile.py
      README.md
```

- `profile.json` 是严格的 CaseProfile v1 权威；`profile.py` 是固定的 fail-closed factory。
- `resources/expected-value.json` 是 scaffold Case 比对的冻结预期 stdout，其摘要绑定在
  `profile.json` 中。
- `cases/*.json` 为 `cernora profile test` 声明每个行为测试行。
- `fixtures/*/` 为每一行保存一个完整的合成 EvidenceBundle v2 package。
- `tests/test_profile.py` 证明 scaffold 可加载且 fail closed；`README.md` 说明权威角色和
  版本升级规则。

`.gitignore` 内容是 `*`，因此 workspace 默认私有。Cernora 不运行 Git 命令，也不会 stage
或发布 Profile。不要 force-add `.cernora/`。

如需创建有意公开的目录，请显式指定：

```sh
cernora profile init my-profile --output profiles/my-profile
```

遇到非法名称、已存在目标或不安全文件系统条目时，初始化会拒绝操作，不会覆盖。

## 权威文件

`profile.json` 是严格的 `CaseProfile` v1 文档，声明：

- 唯一的 Profile identity 和 version；
- 一个或多个 identity 唯一的 Case；
- fixture 引用和精确摘要；
- Scorer Policy 和必选观察；
- Gate Policy 和必选 Score identity。

Profile、Case、fixture、Scorer 或 Gate identity 发生变化时，应视为权威变化。为其他权威
创建的 Evidence 必须 fail closed，不能强制套用到新 Profile。

## 固定 factory

本地加载只执行用户提供目录中的 `profile.py:create_profile()`：

```python
from cernora import Profile


def create_profile() -> Profile:
    return MyProfile()
```

返回对象必须实现 Preview `Profile` 协议：

```python
class Profile(Protocol):
    @property
    def authority(self) -> CaseProfile: ...

    @property
    def projection_version(self) -> str: ...

    def validate_import(
        self,
        package: AuthorityBoundImportPackageV2,
    ) -> None: ...

    def assess(
        self,
        package: AuthorityBoundImportPackageV2,
        context: ProfileEvaluationContext,
    ) -> ProfileAssessment: ...
```

生成的 scaffold 会让 `assess()` 抛出 `NotImplementedError`，避免作者完成 assessment
之前意外判定证据通过。

## 实现 validation

`validate_import()` 应拒绝任何权威不一致或 Profile 特定的结构错误。至少要把绑定的
Profile 和 Case 与 `authority` 比较。如果 command shape、terminal payload 或 Profile
拥有的格式是有效 assessment 的前提，也应在这里检查。

不要推断缺失观察、修复 Producer 字节或读取未声明文件。通用 bundle、artifact、摘要和
封闭目录验证已经由 Importer 负责。

## 实现 assessment

`assess()` 接收不可变、已绑定权威的 package 和 Evaluator 生成的 context，返回包含以下
内容的 `ProfileAssessment`：

- 与给定 evaluation 和 source receipt 绑定的 Evidence v1；
- observation 引用该 Evidence 的 Score v1；
- Scorer Policy 声明的精确必选 observation ID；
- 可选的 Preview `result_records` 类型化结果。

Assessment 必须确定且无副作用。Profile 不能启动工具、访问服务、修改 import package、
发布输出或组合 GateDecision。Deep Evaluator 会交叉检查 identity 和必选 observation，应用
Gate Policy、持久化结果并严格 reload。

当 `result_records` 非空时，每个必选 observation 都必须存在对应的 boolean `outcome` 或
`constraint` record，并与 Score v1 的值、applicability、reason 和 Evidence reference
一致。Deep Evaluator 会验证引用、推导 report validity，并持久化 manifest 绑定的
`evaluation-report.json`。Advisory 和 diagnostic record 可以展示，但不能改变
GateDecision。保持默认值 `()` 即可延续之前不生成 report 的行为。

缺失、格式错误或矛盾的证据不能产生 passing observation。只有充足、有效证据证明行为
失败时，才使用 behavioral false；其他情况应让 evaluation fail closed 为 `inconclusive`。

## 验证与测试

静态 conformance 会检查协议和 canonical authority：

```sh
cernora profile validate --profile-path .cernora/profiles/my-profile
```

该命令会执行受信任的本地 Python，运行前请检查 `profile.py`。静态 conformance 不能证明
assessment 行为正确。

`profile test` 在一个命令中运行完整行为工作流：对每个 `cases/*.json` 行执行静态
conformance 以及真实的 import、evaluation 和严格 reload：

```sh
cernora profile test --profile-path .cernora/profiles/my-profile
```

每一行声明一个 `fixtures/` 下的 `fixture` 子目录，以及 `pass`、`fail`、`inconclusive` 或
`import_rejection` 之一的 `expected` 结果。命令对每一行运行三次，要求持久化结果字节一致，
并输出 canonical JSON 摘要。只有当每一行都确定地符合预期时才返回 `0`；行为不匹配使用
独立的非零退出码，因此 CI gate 不会把“能加载”误认为“能正确评估”。`--output` 选择一次性
输出目录（默认使用临时目录）；`--repetitions` 覆盖默认的三次。

每个声明的 `case_id` 必须属于 Profile authority，并与 fixture bundle 一致。预期的 import
rejection 会保留确定性诊断，包括过期的 Profile、scorer-policy 和 gate-policy authority。
Evaluation 会拒绝并指出缺失的 required observation、不一致的 scorer version，以及未绑定
Evidence reference 的 locator 和 digest。

生成的 scaffold 在实现 `assess()` 之前保持 fail closed。它的 `profile test` 运行会对缺失
证据 fixture 报告 `inconclusive`，并对 completed evidence fail closed，从而证明 scaffold
绝不会悄悄通过。

完整 Profile 测试至少应覆盖：

1. 一次有效 import 和 evaluation，随后严格 reload 结果；
2. 每个必选 observation 的 pass 和 behavioral-fail Case；
3. 格式错误 payload、artifact 损坏和权威不一致；
4. 对相同字节输入重复确定性 evaluation；
5. 不依赖网络、凭证和未声明文件系统内容。

可以把 `builtin:offline-workflow`、`builtin:coding-task`、`builtin:tool-workflow` 和
`builtin:coding-evaluation` 作为打包参考 Profile，但它们不是注册中心。后两者分别展示
工具与 Coding 证据的 structured result；Profile 始终显式选择。Coding 示例只消费冻结的
合成执行 capsule，不展示如何执行不受信任的候选代码。

## 实现 scaffold assessment

生成的 scaffold 的最小已实现 assessment 以 `cernora.examples.profile_authoring` 参考形式
打包。它实现一个必选 observation `claim_grounded`：当且仅当运行记录了一次
`check_value --key alpha` 动作、其 stdout 等于 `resources/expected-value.json`、terminal
claim 等于冻结值、且 claim 的 `evidence_sha256` 等于 stdout SHA-256 时为 `true`。缺失或
基础设施 inconclusive 的证据会输出 `invalid` observation，而不是 behavioral `false`，从而
保持 `inconclusive`。

```python
from cernora.examples.profile_authoring import write_implemented_profile

write_implemented_profile(Path(".cernora/profiles/my-profile"))
```

实现 `assess()` 后重新运行上述两条命令。前三个 fixture 分别报告 `pass`、`fail` 和
`inconclusive`；损坏、authority、scorer-policy 和 gate-policy mismatch fixture 会报告
`import_rejection` 及其确定性诊断。
`scripts/profile_authoring_wheel_check.py` 会在干净项目中从已安装 wheel 重建同一流程，并
不要求凭证、阻断网络访问并拒绝源码 checkout。

## 演进

### `result_records` 迁移

`ProfileAssessment.result_records` 是增量字段，默认值为 `()`，因此现有 Profile 构造函数
无需修改。如需显式选择 structured result，请为每个必选 Score observation 输出版本化
record，使其值、applicability、reason 和 Evidence reference 与 Score v1 一致，并把数值
单位和方向视为 record 契约的一部分。不要自行写入 `evaluation-report.json`；持久化和严格
reload 由 Cernora 负责。

Profile 编写 API 和 Reference Profile 布局属于 Preview。`0.1.x` 内的破坏性变化需要
changelog 和迁移说明，可行时应先弃用。Profile authority 和 projection 要主动版本化，
不能用新含义重新标记旧字节。

### `MetricPlan` 之前的 observation 归属

在共享 Metric SDK 出现之前，Profile 直接拥有其确定性 observation：它从同一份冻结
Evidence 材料输出 `ScoreObservation` 值，可选地输出类型化 `ResultRecord` 值。Deep
Evaluator 校验 identity、证据绑定、必选 observation 顺序和 Gate 一致性，然后持久化并严格
reload 结果。后续的 `MetricPlan` 必须复用这一经过验证的归属形态，而不是重新解释它：每个
Profile 拥有的 observation 映射到一个带显式 validity 状态、数值单位与方向的版本化 metric，
并保留相同的 Evidence reference。权威和决策在该迁移中不能被静默重新解释。
