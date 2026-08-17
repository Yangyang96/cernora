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
      profile.json
      profile.py
```

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
- Scorer Policy 声明的精确必选 observation ID。

Assessment 必须确定且无副作用。Profile 不能启动工具、访问服务、修改 import package、
发布输出或组合 GateDecision。Deep Evaluator 会交叉检查 identity 和必选 observation，应用
Gate Policy、持久化结果并严格 reload。

缺失、格式错误或矛盾的证据不能产生 passing observation。只有充足、有效证据证明行为
失败时，才使用 behavioral false；其他情况应让 evaluation fail closed 为 `inconclusive`。

## 验证与测试

静态 conformance 会检查协议和 canonical authority：

```sh
cernora profile validate --profile-path .cernora/profiles/my-profile
```

该命令会执行受信任的本地 Python，运行前请检查 `profile.py`。静态 conformance 不能证明
assessment 行为正确。

完整 Profile 测试至少应覆盖：

1. 一次有效 import 和 evaluation，随后严格 reload 结果；
2. 每个必选 observation 的 pass 和 behavioral-fail Case；
3. 格式错误 payload、artifact 损坏和权威不一致；
4. 对相同字节输入重复确定性 evaluation；
5. 不依赖网络、凭证和未声明文件系统内容。

可以把 `builtin:offline-workflow` 和 `builtin:coding-task` 作为打包参考 Profile，但它们
不是注册中心。Profile 始终显式选择。

## 演进

Profile 编写 API 和 Reference Profile 布局属于 Preview。`0.1.x` 内的破坏性变化需要
changelog 和迁移说明，可行时应先弃用。Profile authority 和 projection 要主动版本化，
不能用新含义重新标记旧字节。
