# 检查已完成的 Agent Run（Preview）

本入口只检查运行结束后的导出，不启动 Agent、不调用模型，也不执行导出里的命令。
它与 EvidenceBundle v2 导入和 Profile 评测分开，不生成任务级 Gate。

## 最小接入

执行 `uv sync --all-groups`。将[英文教程](agent-run-inspection.md)中的完整合成 JSON
保存为 `run.json`，另建 `reference.json`，内容为 `{"/status":"ready"}`，然后运行：

```sh
uv run cernora agent-run inspect run.json --reference reference.json
```

结果包含调用数、返回数、缺失返回、失败数、耗时和 claims 匹配结果。合成示例得到一次
成功调用和 `1.0` 的字段匹配率。去掉参考参数后为 `inconclusive`。这不是实际调用模型的
验收，也不证明最终自然语言回答正确。

## 导出要求

- 从实际运行记录导出用户任务、最终回答、工具名称、argv 和调用标识。
- 调用标识唯一；返回必须对应此前调用；并行调用允许交错返回。序号从零连续递增，
  时间戳不倒退；唯一 final 事件位于末尾，其 text 与 final_answer 一致。
- 返回明确记录 exit_code 和 timed_out。非零返回码或超时表示工具失败；缺失返回、
  未知返回码、runtime error 表示证据不足，不能按工具成功处理。
- claims 必须来自实际回答，不能从参考答案复制。参考由外部独立提供，以字段路径标签
  映射 JSON 值；`/status` 只是标签，不执行 JSON Pointer。缺失或额外字段计入不匹配；
  布尔值与数字不等同；嵌套 JSON 精确比较；没有 claims 或参考时为 inconclusive。
- 工具输出以 UTF-8 字符串保存在 tool_outputs，摘要映射为相同 ID 的 SHA-256。
  返回引用输出，claims 引用已存在的证据 ID。实际核验字节摘要，不读取外部路径或 URL。
- 先脱敏，再计算脱敏内容的摘要；保留私有原件于自己的忽略目录。不要导出凭证、私有
  推理或内部实现。摘要不能认证来源，也不能代替参考权威。
- conditions 记录外部运行器的版本与 token 预算；Cernora 不保证预算已执行，不验证
  Prompt 实际传输内容。生效配置和成本仍需外部 harness 保存。

Python 可调用 `cernora.evaluation.agent_export.inspect_agent_run(Path("run.json"),
reference={"/status": "ready"})`。`load_agent_run_export` 接受 Path 文件，或 str/bytes JSON。
兼容参数 reference_available 不能代替真实参考，也不能启用评分。

## 判定边界和错误处理

检查器校验引用存在，不推断引用是否语义支持断言；也不判断意图、预期工具/参数选择、
自然语言幻觉或业务正确性。这些需要相应的 Profile 和参考。进程退出 0 不是任务通过。

CLI 返回码：0 为检查有效且未发现已记录的失败；1 为工具失败或已评分字段不匹配；
2 为命令使用错误；3 为非法或不足证据。未调用工具记录为 no_tool_call，claims 仍不足，
不会因有参考而变为成功。合法摘要写 stdout，非法输入错误写 stderr。

导入函数拒绝重复 JSON key、未知字段/版本、孤立或重复返回、摘要不符和悬空引用，
抛出 ContractError。命令不写文件，相同输入重复检查产生相同字节；其幂等性来自只读
操作，不是持久化 bundle 导入。工具执行成功与回答事实性分别输出。

## 兼容性与迁移

公开 JSON Schema 从 Python 模型生成；跨事件关系、序号连续、最终回答绑定、摘要值
以及引用关系仍由运行时检查。只通过 Schema 不能当作全部证据校验通过。

未发布草案中的空工具 payload 需迁移为完整调用/返回结构；消息需有 text，摘要需提供
实际内联输出，重复 claims/标识和悬空证据不再接受。现有 EvidenceBundle v2 与 Profile
接口保持原样；不要把本入口摘要用作 evidence import 输入。

## 未记录信息

conditions.budget 必须出现；未记录总 token 预算时填 null，不要用 0 或超时秒数代替。
已有整数预算仍有效。elapsed_ms 是导出事件的时间戳跨度；如果生产者只记录消息创建时间，
该值不代表完整执行耗时。壁钟耗时和计费应由运行器单独记录。
