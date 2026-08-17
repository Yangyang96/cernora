# `0.1.x` 正式发布流程

[English](release-day-runbook.md) | **简体中文**

这是 Cernora `0.1.x` 的可重复发布流程。请从
`https://github.com/Yangyang96/cernora` 的干净 clone 中运行。Release Owner 是
`Yangyang96`；PyPI 和 TestPyPI 用户名是 `oohchild`。

下面始终使用 `pyproject.toml` 中声明的版本。生产 tag 必须是 `v<version>`。已发布 tag、
GitHub Release artifact 和 package index 文件不可变；任何修正都发布新版本。

## 1. 准备一个发布 commit

1. 把 `pyproject.toml` 和 `src/cernora/__init__.py` 更新为相同版本。
2. 在 `CHANGELOG.md` 中把预定改动从 `Unreleased` 移到
   `## <version> - YYYY-MM-DD`，使用真实 UTC 发布日期。
3. 如果发布改变了 README、安全说明、兼容声明或迁移说明，同步更新。没有所需原生证据时
   不得扩大平台支持声明。
4. 重新检查名称/商标风险、Apache-2.0、`NOTICE`、发布来源、版权主体和公开分发批准。
5. 从仓库根目录运行统一本地检查：

   ```sh
   uv sync --all-groups
   uv run python scripts/release.py preflight
   ```

命令会检查版本/changelog 一致性、测试、Ruff、format、严格 mypy、`git diff --check`，
在隔离目录中全新构建，并检查封闭源码树和两个归档。命令会输出 wheel 与 sdist 的精确
SHA-256。`Unreleased` 非空时命令会拒绝，以免为已发布版本认证后续改动。任何源码字节变化
都会使结果失效。

## 2. 合并并绑定 CI artifact

1. 推送发布分支，通过受保护的 `main` workflow 合并。
2. 要求精确发布 commit 的 Ubuntu Python 3.12/3.13 CI 和 wheel-acceptance job 通过。
3. 记录 commit SHA 和成功的 CI run ID。保留的 `cernora-dist-<commit-sha>` artifact 必须
   恰好包含匹配的 wheel 和 sdist。
4. 发布前比较 CI artifact 与已接受 preflight 的摘要。

`testpypi` 和 `pypi` GitHub environment 继续受 deployment-ref 规则和 Owner 显式批准保护。
Workflow 使用 OIDC Trusted Publishing；GitHub secret 中不得存放 package index 密码或
长期 upload token。

## 3. 可选 TestPyPI 演练

使用唯一 prerelease 版本演练，例如 `0.1.1rc1`；TestPyPI 文件名不能覆盖。调用
`.github/workflows/release.yml`，设置 `target=testpypi`，并提供精确 CI run ID 和 commit
SHA。Workflow 下载经过检查的 CI artifact，并从匹配的 wheel/sdist 推导版本，不重新构建。

演练成功后，在新 commit 中准备最终生产版本，并重新执行完整 preflight 和 CI。不能把
prerelease 字节重新标记成生产版本。

## 4. 发布生产版本

1. 在精确已接受的 `main` commit 上创建 annotated tag `v<version>`，不能移动或替换。
2. 从该 tag 创建 GitHub Release，附上精确已接受的 wheel 和 sdist。
3. 从 `v<version>` 调用 `.github/workflows/release.yml`，设置 `target=pypi`，并使用相同
   CI run ID 和 commit SHA。
4. 批准受保护的 `pypi` environment。Workflow 会验证 CI identity、推导 artifact version、
   要求 tag 等于 `v<artifact-version>`，然后在不重新构建的情况下上传。

## 5. 验证生产发布

从精确 release tag checkout 运行：

```sh
uv run python scripts/release.py verify --version <version>
```

命令下载生产 PyPI 上精确的 wheel 和 sdist，验证公开 SHA-256 与封闭内容，在干净 Python
3.12/3.13 环境中安装 `cernora==<version>`，运行 `pip check`，确认 import 来自各自环境，
重新执行 offline/backend/frontend/fail-closed 验收，并要求两个 Python 版本的结果 manifest
一致。

## 6. 开始下一个版本

发布后新增 `Unreleased`。兼容补丁增加 patch 版本；破坏 Supported Preview 的改动按
兼容性矩阵发布 minor 版本并提供迁移说明。

`v0.1.0`、对应 GitHub Release artifact 和 PyPI 文件已经永久封闭。后续版本沿用相同规则：
不能编辑已发布字节，也不能移动已发布 tag。
