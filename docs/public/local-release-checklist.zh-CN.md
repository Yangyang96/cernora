# 本地发布检查清单

[English](local-release-checklist.md) | **简体中文**

这份清单用于准备交给 Owner 评审的 Cernora release candidate。它不会发布 package、创建
远程仓库、推送分支、创建 tag，也不表示名称或商标已经获批。

请在全新的公开 Cernora checkout 中运行，使用 Python 3.12 或 3.13，并准备好锁定的开发
环境。

## 1. 核对发布意图

- [ ] `CHANGELOG.md` 在精确版本和 UTC 日期下描述目标发布；后续工作放入新的
  `Unreleased`。
- [ ] README 和验收材料把 Cernora 称为独立评测内核，不声称打包的合成导出运行了
  Agent Runtime 或 sandbox。
- [ ] Package metadata、`cernora.__version__` 和 artifact 名称中的版本一致。
- [ ] Supported Preview 或 Preview 变化附带所需迁移说明。
- [ ] Release Owner 重新检查名称可用性、所有权和法律批准。
- [ ] `LICENSE` 是标准 Apache License 2.0，`NOTICE` 与发布来源一致且不虚构组织。
- [ ] 平台表分别列出 Linux、Windows 和 macOS，不把 universal wheel tag 或代码评审当作
  原生执行证据。

## 2. 运行源码检查

```sh
uv sync --all-groups
uv run python scripts/release.py preflight
```

统一命令会运行源码检查，在全新临时目录构建，检查封闭目录树和 artifact，离线安装刚构建的
wheel，并在输出 artifact SHA-256 前运行完整 Profile authoring 验收。CI 会在两个支持的
Python minor 版本上重复 wheel 验收。测试输出不完整或不可读时，不能接受 release candidate。

## 3. 检查公开目录树

- [ ] 只包含有意公开的根目录治理文件、package、测试、示例、文档、CI 和发布检查文件。
- [ ] 不含嵌套仓库元数据、旧 ref、编排状态、私有原始证据、cache、environment、构建输出
  或开发归档。
- [ ] 每个成员都是普通文件；不存在符号链接或意外的大文件。
- [ ] 扫描文本和文件名，排除凭证、个人路径、私有端点和非公开产品词汇。
- [ ] Markdown 相对链接能在公开树内解析，文档命令与当前 CLI help 一致。

## 4. 检查 artifact

Preflight 会确认全新构建只生成一个 wheel 和一个与 `project.version` 一致的源码归档。
重新检查已有 `dist/` 目录时运行：

```sh
uv run python scripts/check_release.py --tree . --dist-dir dist
```

还需确认：

- [ ] wheel 只包含 `cernora/` 和对应 distribution metadata；
- [ ] 打包的 Schema、Reference Profile 资源和离线示例都存在；
- [ ] 源码归档成员恰好是公开树白名单加生成的 package metadata；
- [ ] artifact 不含仓库元数据、cache、公开集合之外的测试、凭证、个人路径或未声明大文件；
- [ ] 安装后 metadata 声明 Apache-2.0、Python 3.12/3.13 和且仅有已声明依赖。

## 5. 验证 wheel-only 运行

在 checkout 外创建干净目录并安装 wheel。离线检查时，先准备含 Cernora wheel 和所有已声明
依赖的本地 wheelhouse，再只从 wheelhouse 安装：

```sh
cernora_check_dir="$(mktemp -d)"
python -m venv "$cernora_check_dir/venv"
"$cernora_check_dir/venv/bin/python" -m pip install \
  --no-index --find-links ./wheelhouse cernora==<version>
cd "$cernora_check_dir"
"$cernora_check_dir/venv/bin/python" -m cernora.examples.offline_workflow ./run
```

最后一条命令必须输出 `pass`。在三个新目录中重复运行并比较有意保持一致的 canonical
输出。确认进程不读取源码 checkout、不访问网络，也不需要凭证。

在一次性 run 中损坏复制的 bundle 或 artifact，确认对应 import/evaluation 会 fail closed，
不会通过。

wheel-only 检查从打包的合成 completed export 开始，只能记录为 evaluation-core 验收；
它不能验证 Agent 启动、sandbox policy、runtime receipt 捕获或 Experiment Harness 行为。

统一 preflight 还会从隔离 wheel 安装运行 `scripts/profile_authoring_wheel_check.py`。它会创建
私有 Profile、实现引导式 assessment，并要求确定性的 `pass`、`fail`、`inconclusive` 和
import-rejection 结果。

## 6. 检查发布历史

- [ ] 公开源码 commit 从最终白名单目录树创建，不含私有 Evaluator 仓库元数据或历史。
- [ ] 已有正常仓库初始化 commit 有记录，未引入 force push 或无关 ref。
- [ ] 创建源码 commit 后，发布 staging clone 的 `git status --short` 为空。
- [ ] 在创建 tag 或上传前记录 commit tree digest 和 artifact digest。

## 7. 记录发布 checkpoint

记录精确命令、工具版本、退出状态、tree digest 和 artifact digest。只有当前 Release Goal
到达相应远程 checkpoint 后，才能 push、upload、tag 或宣布发布。

后续远程操作和不可变的 `0.1.1+` 流程见[正式发布流程](release-day-runbook.zh-CN.md)。完成
这份清单后，任何源码字节变化都会使上述构建和摘要证据失效。
