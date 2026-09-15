# 首次接入：从完成态记录到评测决策

[English](first-integration.md)

本教程使用中立合成记录，要求 Python 3.12 或 3.13，以及当前 checkout 构建的 wheel。
新检查示例尚未发布；安装后不需要 Agent、模型、凭证或网络服务。

## 在仓库外独立安装

在仓库根目录执行：

```sh
uv sync --all-groups
uv run python -m build --wheel --outdir /tmp/cernora-onboarding-dist
uv venv /tmp/cernora-onboarding-venv --python 3.13
uv pip install --python /tmp/cernora-onboarding-venv/bin/python /tmp/cernora-onboarding-dist/cernora-0.1.4-py3-none-any.whl
mkdir /tmp/cernora-onboarding-project
cd /tmp/cernora-onboarding-project
. /tmp/cernora-onboarding-venv/bin/activate
```

已有同名目录时换用新路径。后续命令均在仓库外的新项目中执行，输出路径不得已存在。

## 自动生成检查导出

以下命令生成四份合成原生记录及独立参考文件。示例自动配对调用与结果、生成连续事件序号、
保留时间戳、映射实际结构化 claims，并计算 stdout 摘要，无需手写导出协议 JSON：

```sh
python -m cernora.examples.minimal_adapter fixtures records
python -m cernora.examples.minimal_adapter export records/success.json success.json
cernora agent-run inspect success.json --reference records/reference.json
```

预期退出码 `0`、`tool_succeeded: true`、`state: "evidence_available"`、claims 准确率 `1.0`。
**这只是检查结果，不是任务通过判定。**

另三条路径分别运行；下列非零退出码是预期结果：

```sh
python -m cernora.examples.minimal_adapter export records/failure.json failure.json
cernora agent-run inspect failure.json --reference records/reference.json
# 退出 1：工具完成，但记录的 claim 与参考值不符

python -m cernora.examples.minimal_adapter export records/missing-evidence.json missing.json
cernora agent-run inspect missing.json --reference records/reference.json
# 退出 3：缺少工具结果，inconclusive，不补造成功

python -m cernora.examples.minimal_adapter export records/field-error.json invalid.json
# 退出 3：未知字段 exitCode 被拒绝，不生成 invalid.json
```

适配器不读取 `reference.json`。失败记录保留实际错误值；修改参考只影响检查评分，不改变导出。
相同记录导出到不同新路径，字节相同。无效 JSON、重复键、未知字段/版本、悬空 claim 引用、
不一致时间顺序均被拒绝；不会覆盖已有文件。

## 完整 Profile 评测

`inspect` 接收 `agent-run-export/v1`，输出观察结果。完整评测接收与 Profile、Case、fixture
权威绑定的 **EvidenceBundle v2**，持久化 Evidence、Score、GateDecision，并严格重载身份和摘要。
检查报告不能作为 bundle 导入；检查退出 `0` 不能用作任务 Gate。

下面是另一个中立 lookup 任务。已有 `OfflineWorkflowAdapter` 将合成完成态记录转换为 bundle，
随后自动导入、评测和严格重载：

```sh
python -m cernora.examples.offline_workflow full-evaluation
# pass

cernora evidence import --profile builtin:offline-workflow \
  --bundle full-evaluation/bundle/bundle.json --output imported
cernora evidence evaluate --profile builtin:offline-workflow \
  --import-root imported --output evaluated
```

查看 `evaluated/gate-decision.json`、`evaluated/score.json` 和 `evaluated/evidence.json`。
需要经过校验的结果时，用匹配的 Profile 严格读取：

```sh
python - <<'PY'
from pathlib import Path
from cernora import read_imported_evaluation
from cernora.profiles.offline_workflow import OfflineWorkflowProfile

print(read_imported_evaluation(Path("evaluated"), OfflineWorkflowProfile()).case_outcome)
PY
```

预期打印 `pass`。该 fixture 证明评测链路可运行；它不是对你自己的 Agent 的评测，也不是把
前面的 status 检查结果自动转换成 Profile 结论。

## 创建并验证自己的评分规则

生成私有 scaffold，写入随 wheel 提供的最小参考实现，再通过实际导入、评测和严格重载验证：

```sh
cernora profile init my-profile
python - <<'PY'
from pathlib import Path
from cernora.examples.profile_authoring import write_implemented_profile

write_implemented_profile(Path(".cernora/profiles/my-profile"))
PY
cernora profile validate --profile-path .cernora/profiles/my-profile
cernora profile test --profile-path .cernora/profiles/my-profile
```

测试命令退出 `0` 表示七类预期结果各重复三次均一致：`pass`、`fail`、`inconclusive`，以及
工件损坏、Profile/评分/Gate 权威不匹配的四类 `import_rejection`。它不表示所有 fixture 都通过。
未实现 assessment 的原始 scaffold 无法授予 pass。

真实接入时，先用冻结任务规则和独立参考替换演示 assessment 与 fixture 权威，再将自己 Adapter
生成的 bundle 传给前面的 import/evaluate 命令；两条命令都把
`--profile builtin:offline-workflow` 替换为 `--profile-path .cernora/profiles/my-profile`。
权威更新与证据要求见 [Profile 开发](profile-authoring.zh-CN.md) 和
[Adapter 一致性](adapter-conformance.zh-CN.md)。

## 可复用部分与需要实现的部分

| 层 | 可复用 | 你需要完成 |
| --- | --- | --- |
| Runtime / harness | 已有 Agent runner | 运行任务，记录实际配置、调用和结果、stdout/stderr、退出/超时、最终回答、墙钟与实测成本。 |
| 检查适配器 | 本例 `adapt_record` / `export_record` | 将 runner 的完成态数据映射成示例原生记录，或按实际格式调整映射。 |
| Bundle Adapter | `OfflineWorkflowAdapter` 窄范围参考、一致性检查工具 | 按自己的 Profile 契约转换完成态证据，绑定工件/回执及权威，不补造缺失事实。 |
| Profile | 私有 scaffold、参考 assessment、确定性测试链路 | 在评测前定义成功标准、证据充分性、独立参考和必需观察。 |
| 评测核心 | import、evaluate、strict reload、batch、comparison | 提供完整证据并显式选择匹配权威。 |

最小检查示例只支持顺序调用。缺失结果、stdout 和预算保留为未知；`stderr` 留在原生记录，
当前检查投影仅使用 stdout 证据。示例不捕获 runtime 错误、并发事件交错、完整会话、账单或回执
权威。对真实 runtime 应按其实际事件扩展映射，不要为了套示例重排并发事件。
claims 必须来自实际最终结构化输出，不能从预期答案或未经审计的文本提取中补造。
引用存在也不等于引用内容支持断言。

做改前/改后比较时，先冻结事件组、开发/验证划分、参考、Profile 和实际执行条件，再只改一个
变量；失败和缺证 Trial 都须保留，成本另行实测，使用
[受控比较](controlled-comparison.zh-CN.md) 链路。这些合成示例不证明干预收益或生产稳定性。

## 验收与迁移

独立 wheel 验收脚本通过隔离 Python 子进程重复上述操作：

```sh
/tmp/cernora-onboarding-venv/bin/python -I /path/to/checkout/scripts/onboarding_wheel_check.py \
  --output /tmp/cernora-onboarding-acceptance
```

它拒绝从源码导入，并检查四条路径退出码、字节确定性、字段错误不产出文件、完整 Profile Gate
以及七类 authoring 结果。`summary.json` 保存解释器、版本和结果。这是可复核的命令验收，
不冒称已完成独立真人可用性研究。

示例为增量功能，不改变已有公共协议、API 或评测语义。`synthetic-completed-record/v1` 是示例
原生格式，不是通用 Runtime Connector 契约；已有 bundle 无需迁移，检查导出不可改名冒充 v2 bundle。
