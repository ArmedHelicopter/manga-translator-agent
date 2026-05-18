# External-First 安全审计纪要

日期：2026-05-16

## 背景

这是一份针对本轮 external-first 架构收口的内部安全审计纪要。目标不是宣称“系统已经完全安全”，而是明确：

- 哪些风险会阻断本次 release
- 哪些风险已经被本轮收敛
- 哪些风险仍然存在，但当前按本地或可接受风险处理

本轮重点覆盖：

- secrets hygiene
- provider config 边界
- external subprocess 调用
- benchmark/debug/review artifact 泄露面
- `.gitignore` 与 tracked/untracked 发布边界

## Blocking

### 1. 本地 provider 配置不得进入版本库

要求：

- `configs/providers.toml` 必须保持未追踪
- 文档只允许引用 `configs/providers.toml.example`
- release 前必须确认工作树中没有真实 API key 或自定义 endpoint 凭据

当前状态：

- 已通过 `.gitignore` 隔离 `configs/providers.toml`
- 本次 release 仍需在提交前再次确认未被追踪

### 2. benchmark/debug/review 大产物不得混入 release

要求：

- `data/`
- `benchmark/`
- `debug/`
- review 输出目录
- external vendor repo

都不得作为 release 内容提交。

当前状态：

- `.gitignore` 已覆盖 `data/`、`external/`、benchmark/debug 相关目录
- release 前仍需用 `git status` 做最终确认

## Warning

### 1. external baseline summary 不应长期暴露过多运行环境细节

历史风险：

- `external-baseline-summary.json` 曾包含完整 `PATH`、`LD_LIBRARY_PATH`、`LD_PRELOAD`
- 这类信息对排障有用，但不适合长期作为默认产物保留

本轮处理：

- 收敛为布尔化 runtime env 摘要
- 保留必要的 provider/model/returncode/artifact 索引
- 移除不必要的完整环境路径落盘

### 2. provider preflight 会输出 base_url

风险性质：

- 自定义兼容端点本身可能属于敏感基础设施信息
- 但在当前阶段，这一信息对于排查 external/internal 网络链路问题是必要的

当前处理：

- 允许在本地运行日志中出现
- 不建议把包含这类日志的大文件作为 release artifact 提交

### 3. external subprocess 继承环境仍需持续审查

当前实现已经：

- 去掉 `CONDA_*`
- 去掉 `PYTHONPATH`
- 去掉 `PYTHONHOME`
- 收紧 `LD_LIBRARY_PATH` / `LD_PRELOAD`

但后续如果 external runtime 再扩展更多 provider/env，仍需重新审计命令边界与变量传递面。

## Accepted Local-Only Risk

### 1. 本地 `configs/providers.toml` 视为本地隔离文件

本轮默认不把它按“已泄露 secret”事件处理。

前提是：

- 文件未被追踪
- 文件内容未进入提交历史
- 未被复制进 benchmark/review/report 产物

如果后续发现任何一项失守，应立刻升级为 secret rotation 事件。

### 2. external 仓库与独立 venv 保持本地依赖

当前 external baseline 依赖：

- 本地 clone 的 `manga-image-translator`
- 独立 `.external-mit-venv`

这属于可接受的本地开发依赖，但不应被纳入本仓库 release 边界。

## Release Discipline

本次 external-first baseline release 前必须满足：

1. `git status` 中只包含本次计划内的代码与文档改动
2. 无本地 secret、provider config、benchmark/debug/review 大产物被追踪
3. external vendor repo 未被纳入版本库
4. 测试覆盖至少包括 schema/config/benchmark/external CLI 相关用例
5. release tag 只表达“external-first baseline established”，不表达成熟度或完备安全性

## 结论

当前最重要的安全结论不是“external-first 更危险”，而是：

> external-first 路线把发布边界和 artifact hygiene 变得更重要了。

本轮已经收敛的点：

- 本地 provider config 隔离
- benchmark/debug/review 目录忽略策略
- external summary 的环境字段最小化

本轮仍需持续关注的点：

- provider/base_url 日志暴露面
- external 子进程环境传递边界
- release 前工作树与 tag 边界检查
