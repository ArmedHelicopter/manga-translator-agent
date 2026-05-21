<!-- /autoplan restore point: /home/exusiai/.gstack/projects/manga-translator-agent/mga-layer-bootstrap-autoplan-restore-20260518-201635.md -->
# External-Core Migration Plan

## Goal

把当前 fork 出来的 `manga-image-translator` 新仓，收敛成 `mga` 的正式主仓：

- external runtime 继续作为核心宿主
- `mga` 提供 orchestration、artifacts、benchmark、review、memory/wiki、QA 的上层能力
- 旧仓 `manga-translate-agent` 降级为 research / legacy archive

这份计划只描述 **新仓内** 还需要完成的工作。

## Current State

当前新仓已经具备：

- 已迁入 `docs/PRD.md`、`docs/SPEC.md`、`docs/analysis/`、`docs/research/`
- 已迁入 `mga/artifacts/`、`mga/benchmark/`、`mga/config/`、`mga/runtime_bridge/`
- 已迁入 `tests/runtime/`、`tests/benchmark/`、`tests/fixtures/`
- `.gitignore` 已修正，`tests/benchmark/` 不再被误忽略

当前新仓仍未完成：

- 正式 `README.md` 仍然是 external 原仓口径
- `README.mga-draft.md` 还没有转正
- `mga/` 还不是一个完整、清晰的 Python 包层
- `translate` / `benchmark-external` / `review` 还没有在新仓里形成正式入口
- memory/wiki、QA、learn-from 还只是文档设计，未接入新宿主

## Phase 1: Repo Identity And Packaging

### 1. Rewrite the repository front door

- 用 `README.mga-draft.md` 为基础，重写根 `README.md`
- README 开头必须明确：
  - 这是基于 `manga-image-translator` runtime 的 `mga` 主仓
  - external runtime 是 core
  - `mga` 是 orchestration + intelligence layer
- README 必须包含：
  - 一句话定位
  - 三层架构图
  - 默认命令入口
  - benchmark / review 入口
  - legacy/research 资产说明

### 2. Turn `mga/` into a real package

- 补 `mga/__init__.py`
- 视需要补：
  - `mga/artifacts/__init__.py`
  - `mga/benchmark/__init__.py`
  - `mga/config/__init__.py`
  - `mga/runtime_bridge/__init__.py`
- 明确 `mga/` 目录职责：
  - `artifacts/`：统一产物落盘
  - `benchmark/`：评测与报告
  - `runtime_bridge/`：external 宿主桥接
  - `config/`：`mga -> external runtime` 配置桥接

### 3. Decide naming and import policy

- 保持顶层目录名暂时为 `mga/`
- 不迁移旧仓 `models/`
- 新仓如果需要结构化对象，后续按 external-core 语义重新定义
- 禁止继续把旧 internal schema 原样作为新主仓核心合同

## Phase 2: Formal Runtime Entrypoints

### 4. Add a minimal `mga` CLI layer

- 在新仓中新增最小 CLI 入口，建议形态：
  - `translate`
  - `benchmark-external`
  - `review`
  - `legacy` 或 `research` 预留分组
- 默认 `translate` 必须：
  - 调用 external runtime
  - 统一保存 `manifest.json`
  - 统一保存 external 原始文本 artifact
  - 统一保存 normalized text artifact
  - 统一保存 `run.json`

### 5. Bridge config into external runtime

- 定义新仓里的配置来源：
  - provider key
  - base_url
  - model
  - 输出目录
  - artifact 策略
- external runtime 配置文件只承接运行参数
- preflight 检查必须在 `mga` 层完成：
  - runtime repo 是否完整
  - python 可执行文件是否可用
  - 配置是否存在
  - provider 参数是否齐全

### 6. Normalize outputs into stable artifacts

- `translate` 执行后至少落盘：
  - `manifest.json`
  - `external-baseline-summary.json` 或更名后的 runtime summary
  - `external-baseline-text.txt`
  - `external-baseline-text-normalized.json`
  - `run.json`
- 如果 external runtime 输出最终图片：
  - 要在 README 中写明默认输出位置
  - 要在 summary 里记录 rendered image 列表

## Phase 3: Benchmark And Review First

### 7. Make benchmark/report the first stable `mga` feature

- 优先保证以下能力能在新仓稳定运行：
  - external translation benchmark
  - same-page review
  - multi-page review
  - external text normalization
- 不要求第一阶段先接 memory/wiki 或 persona QA
- benchmark 的定位要写死：
  - 它不是附属脚本
  - 它是 `mga` 的核心工程能力之一

### 8. Re-home the migrated tests

- 把已迁入测试整理成更清晰层级：
  - `tests/runtime/`
  - `tests/benchmark/`
  - `tests/fixtures/`
- 当前 `tests/README.md` 需要补说明：
  - 哪些测试覆盖 runtime bridge
  - 哪些覆盖 benchmark
  - 哪些是后续 memory/wiki 预留

### 9. Add a smoke validation target

- 新仓需要一个最小 smoke 路径，至少验证：
  - 配置加载
  - external runtime 调用命令拼装
  - artifact 落盘
  - benchmark report 生成
- 目标不是完整翻译质量验收
- 目标是保证“新主仓作为宿主层”能稳定工作

## Phase 4: Intelligence Layer Re-attach

### 10. Re-introduce memory/wiki only after the host path is stable

- 等 `translate`、`benchmark-external`、`review` 稳定后，再开始接：
  - memory/state
  - wiki projection
  - explicit sync
  - retrieval
- memory/wiki 必须挂在 `mga intelligence layer`
- 不直接侵入 external runtime 核心代码

### 11. Re-introduce QA and translation brain in order

- 顺序固定为：
  1. translation artifact normalization
  2. translation brain 插入点
  3. QA evidence layer
  4. memory/wiki write-back
  5. persona consistency / relationship constraint
- 不要在宿主入口未稳定前就上角色系统

## Suggested Commit Sequence

建议后续在新仓按这个顺序提交：

1. `docs: rewrite repository README around external-core mga architecture`
2. `chore: turn mga into a formal package layer`
3. `feat: add minimal mga cli for translate and benchmark-external`
4. `feat: normalize external runtime artifacts and run summaries`
5. `test: add smoke coverage for runtime bridge and artifact flow`
6. `docs: document benchmark and review as first-class mga capabilities`
7. `feat: add memory wiki scaffolding on top of external-core host`

## Done Criteria

新仓达到下面这些条件，才算完成“从迁移资产到可工作的主仓”：

- 根 README 已转成 `mga` 口径
- `mga/` 是正式包层，不只是复制进来的代码目录
- `translate` 默认走 external runtime
- `benchmark-external` 可稳定输出统一报告
- review 脚本和文档能在新仓语义下工作
- 测试目录结构清晰、可运行
- memory/wiki 和 QA 的接入顺序已在新仓文档里固定

## Explicit Non-Goals For This Round

- 不在这一轮迁移旧仓 internal `models/`
- 不在这一轮把旧 internal pipeline 也搬成新仓一等主线
- 不在这一轮做全量 UI
- 不在这一轮做双向无损 memory/wiki 同步
- 不在这一轮承诺完全替换 external runtime 内部实现

## GSTACK REVIEW REPORT

| Run | Skill | Status | Verdict | Notes |
|---|---|---|---|---|
| 1 | `office-hours` | completed | reframed | 产出新的 branch design doc，旧 external-core host framing 被用户明确否决 |
| 2 | `autoplan` Phase 1 | completed | challenge | CEO 视角认为当前 plan 的核心问题是 thesis 已过时，需先重写成功标准 |
| 3 | `autoplan` Phase 2 | skipped | no UI scope | 计划仅出现零散 `form` 词命中，不构成真实 UI review 范围 |
| 4 | `autoplan` Phase 3 | completed | concern | 工程重点应从“正式 host 层入口”转为“post-OCR seam + reorder stage + contract split” |
| 5 | `autoplan` Phase 3.5 | completed | concern | DX 重点是 staged runtime contracts、smoke path、future CLI semantics，而不是先包装成熟宿主 |

## AUTOPLAN REVIEW REPORT

### Here's what I'm working with

- 当前 `plan.md` 仍然是 **external-core migration plan**
- 用户在 office-hours 里把 thesis 改成了：
  `This repo is an intention-driven pipeline interceptor, and success in this round means decoupling the upstream monolith to expose a stable seam where an agent can orchestrate the text immediately after OCR.`
- UI scope: `no`
- DX scope: `yes`
- 新 design doc 已写入：
  `/home/exusiai/.gstack/projects/manga-translator-agent/exusiai-mga-layer-bootstrap-design-20260519-080334.md`

### Phase 1: CEO Review

#### 0A. Premise challenge

- 当前 plan 解决的是“如何把仓库收敛成 external-core host layer”
- 用户当前要解决的是“如何把单体 runtime 切开，在 OCR 后暴露 agent seam”
- 这不是 wording 调整，而是产品对象改变：
  - 从 `host around external runtime`
  - 变成 `interceptor inside runtime`

结论：
- 旧 premise 1 错了：这个 round 的主角不是 README / packaging / formal CLI
- 旧 premise 2 也错了：`mga/` 不是这轮的核心 architectural center
- 真正的 this-round leverage 在 runtime core cut，而不是 repo front door

#### 0B. Existing code leverage

What already exists:

- OCR output containers and text aggregation live in [manga_translator/utils/textblock.py](/home/exusiai/_dev/manga-translator-agent/manga_translator/utils/textblock.py).
- Text region grouping logic already exists in [manga_translator/textline_merge/__init__.py](/home/exusiai/_dev/manga-translator-agent/manga_translator/textline_merge/__init__.py).
- Runtime orchestration still flows through [manga_translator/__main__.py](/home/exusiai/_dev/manga-translator-agent/manga_translator/__main__.py) and [manga_translator/mode/local.py](/home/exusiai/_dev/manga-translator-agent/manga_translator/mode/local.py).
- Current migrated benchmark/artifact work in [mga/benchmark](/home/exusiai/_dev/manga-translator-agent/mga/benchmark) and [mga/runtime_bridge](/home/exusiai/_dev/manga-translator-agent/mga/runtime_bridge) is still useful as validation tooling, but it no longer defines the main product direction.

Sub-problem to existing code map:

| Sub-problem | Existing code | Reuse posture |
|---|---|---|
| OCR line extraction | `manga_translator/ocr/*` | preserve |
| OCR line grouping / region merge | `manga_translator/textline_merge/__init__.py` | refactor around |
| Text container semantics | `manga_translator/utils/textblock.py` | probably wrap or evolve |
| Runtime control flow | `manga_translator/__main__.py`, `manga_translator/mode/local.py` | split into stages |
| Benchmark validation | `mga/benchmark/*`, `tests/benchmark/*` | keep as downstream validation |

#### 0C. Dream state mapping

```text
CURRENT STATE                  THIS ROUND                     12-MONTH IDEAL
upstream-like monolith   --->  explicit OCR seam       --->  agent-native staged runtime
OCR->translate hidden         OCR->reorder->agent            memory/reasoning operate on
inside runtime flow           boundary exists                stable runtime contracts
```

#### 0C-bis. Implementation alternatives

APPROACH A: OCR Hook Patch
  Summary: Inject a reorder callback after OCR with minimal runtime surgery.
  Effort:  M
  Risk:    Medium
  Pros:
  - Fastest proof that post-OCR interception is possible.
  - Lower immediate blast radius.
  Cons:
  - Seam likely remains too implicit.
  - Future agent orchestration still fights monolith assumptions.
  Reuses:
  - Existing OCR and translation path almost unchanged.

APPROACH B: Contract-First Stage Split
  Summary: Refactor the runtime into explicit `ocr -> reorder -> translate -> render` stages with a stable post-OCR contract.
  Effort:  L
  Risk:    Medium
  Pros:
  - Best fit for the user’s stated success criteria.
  - Makes reorder and future agent logic first-class runtime stages.
  Cons:
  - More invasive now.
  - Forces contract and failure semantics decisions early.
  Reuses:
  - Existing OCR, merge, and rendering primitives, but under clearer boundaries.

APPROACH C: Intention IR Runtime
  Summary: Introduce a new IR after OCR and run reorder, memory, and reasoning directly on it.
  Effort:  XL
  Risk:    High
  Pros:
  - Closest to end-state vision.
  - Strongest long-term product story.
  Cons:
  - Too much scope for this round.
  - Easy to slide into full rewrite.
  Reuses:
  - Mostly concepts, not much implementation surface.

RECOMMENDATION:
- Choose B. It is the smallest option that actually creates the seam the user asked for.

#### 0D. Mode-specific analysis

Autoplan auto-decision:
- Use **SELECTIVE EXPANSION** logic, but expansion is not the point here.
- Keep scope centered on the seam.
- Reject unrelated host-layer work from Phase 1 of the old plan unless it directly supports the seam.

#### 0E. Temporal interrogation

HOUR 1:
- Implementer needs a precise cut map of current OCR-to-translation flow.

HOUR 2-3:
- Ambiguity hits around whether post-OCR contract wraps current `TextBlock` or replaces it.

HOUR 4-5:
- Surprise will be hidden assumptions in downstream translation and dictionary application that currently expect existing text ordering.

HOUR 6+:
- They will wish the seam had fixtures, smoke tests, and benchmarkable reorder outputs from day 1.

#### 0F. CEO conclusion

The current plan is strategically misaligned with the user’s now-explicit thesis. The repo front-door and package formalization work is not useless, but it is no longer the primary path to value in this round.

#### CEO DUAL VOICES — CONSENSUS TABLE

```text
═══════════════════════════════════════════════════════════════
  Dimension                           Claude  Codex  Consensus
  ──────────────────────────────────── ─────── ─────── ─────────
  1. Premises valid?                   no      n/a     DISAGREE WITH CURRENT PLAN
  2. Right problem to solve?           no      n/a     CURRENT PLAN MISFRAMED
  3. Scope calibration correct?        no      n/a     TOO HOST-LAYER HEAVY
  4. Alternatives sufficiently explored?partial n/a    NEEDS NEW ALTERNATIVES
  5. Competitive/market risks covered?partial n/a      SECONDARY THIS ROUND
  6. 6-month trajectory sound?         weak    n/a     BETTER WITH STAGED SEAM
═══════════════════════════════════════════════════════════════
```

Codex was unavailable in-session, so this phase ran in `[subagent-only]` style under autoplan degradation rules.

#### Error & Rescue Registry

| Method / Codepath | What can go wrong | Exception class / failure shape | Rescued? | User sees |
|---|---|---|---|---|
| `ocr -> reorder` seam | malformed post-OCR contract | schema mismatch | no | runtime failure unless contract validated |
| reorder stage | invalid reading-order assumptions | logical reorder corruption | partial | wrong translation order, silent quality drop |
| reorder -> translate handoff | downstream expects old ordering semantics | integration regression | no | translated text misgrouped or untranslated |
| existing dict application | reorder changes text sequence before dictionary pass | behavior drift | no | subtle text mismatch |

#### Failure Modes Registry

| Codepath | Failure mode | Rescued? | Test? | User sees? | Logged? |
|---|---|---|---|---|---|
| post-OCR contract build | field mismatch or missing lines | N | N | crash or silent drop | N |
| reorder stage | reordered text no longer maps to downstream blocks | N | N | broken translation ordering | N |
| translate handoff | downstream code assumes old merged shape | N | N | partial wrong output | N |

Any row above is a **critical gap** until seam fixtures and smoke tests exist.

### Phase 2: Design Review

Skipped. No meaningful UI scope was detected in the plan.

### Phase 3: Eng Review

#### Step 0: Scope challenge

The old plan’s complexity is pointed at the wrong modules. It expands docs, package boundaries, CLI identity, and artifact norms before identifying the core runtime cut. For this thesis, the minimum successful slice is:

1. identify the OCR output boundary
2. define a post-OCR contract
3. add reorder stage
4. hand off to existing translate/render path
5. validate with smoke tests

That is the smallest complete engineering slice.

#### 1. Architecture review

Required architecture cut:

```text
CURRENT
detect/ocr/merge/translate/render
        all coupled in runtime flow

TARGET THIS ROUND
detect -> ocr -> post_ocr_contract -> reorder -> translate -> render
                         |
                         +-> future agent seam
```

Dependency graph recommendation:

```text
__main__/mode.local
    -> pipeline orchestrator
        -> OCR stage
        -> post-OCR contract builder
        -> reorder stage
        -> translation adapter
        -> render stage
```

Main finding:
- The plan should move its center of gravity from `mga` packaging into the runtime execution graph.

#### 2. Code quality review

Findings:
- Current migrated `mga/*` layer still imports a non-present `manga_translate` package surface. That means the host-layer branch is not just incomplete, it is anchored to a thesis the user no longer wants as primary.
- Existing runtime code still applies pre/post dictionaries around current translation flow in [manga_translator/__main__.py](/home/exusiai/_dev/manga-translator-agent/manga_translator/__main__.py). A reorder stage will likely force clearer ownership of when text is canonicalized.

#### 3. Test review

NEW CODEPATHS:
- build post-OCR contract
- reorder stage execution
- reorder-to-translate adapter
- smoke path through staged runtime

NEW ERROR/RESCUE PATHS:
- invalid OCR contract
- reorder returns incompatible ordering
- downstream translator receives unexpected structure

ASCII test diagram:

```text
CODE PATHS
[+] OCR output capture
  ├── [GAP] schema serialization / validation
  └── [GAP] fixture comparison against current flow

[+] reorder stage
  ├── [GAP] preserves all source text units
  ├── [GAP] changes ordering predictably
  └── [GAP] handles single-line and multi-bubble edge cases

[+] translate adapter
  ├── [GAP] downstream consumes reordered units
  └── [GAP] fallback path when reorder is disabled

USER / RUNTIME FLOWS
[+] single image staged smoke path
  ├── [GAP] end-to-end local mode through new seam
  └── [GAP] artifact/log evidence for seam correctness
```

Test plan artifact summary:
- Required now: seam fixtures, reorder unit tests, one staged smoke path.
- Nice later: benchmark set measuring reorder impact on downstream quality.

#### 4. Performance review

No first-order performance issue dominates this round. The bigger risk is correctness regression, not latency. Still:

- post-OCR contracts should avoid repeated lossy re-materialization
- reorder should operate on existing text primitives, not duplicate full image data

#### Eng conclusion

The engineering plan should no longer start with README/package/CLI formalization. It should start with runtime stage splitting and a seam contract after OCR.

#### ENG DUAL VOICES — CONSENSUS TABLE

```text
═══════════════════════════════════════════════════════════════
  Dimension                           Claude  Codex  Consensus
  ──────────────────────────────────── ─────── ─────── ─────────
  1. Architecture sound?               partial n/a     NEEDS STAGE SPLIT
  2. Test coverage sufficient?         no      n/a     GAPS
  3. Performance risks addressed?      mostly  n/a     SECONDARY
  4. Security threats covered?         partial n/a     CONTRACT HYGIENE NEEDED
  5. Error paths handled?              no      n/a     GAPS
  6. Deployment risk manageable?       partial n/a     ONLY AFTER SMOKE PATH
═══════════════════════════════════════════════════════════════
```

### Phase 3.5: DX Review

This is a developer-facing toolchain repo, so DX still matters. But the critical DX is different now.

#### Developer persona card

Who:
- contributor or future maintainer extending a staged manga translation runtime

Context:
- trying to understand where to inject agent logic without breaking OCR/translation/rendering

Tolerance:
- low tolerance for hidden coupling and undocumented contracts

Expects:
- explicit stage boundaries, fixtures, smoke tests, and commands that reflect the architecture

#### Developer empathy narrative

“I open the repo and the README tells me an external-first host story. But the code still has a lot of upstream runtime structure, and the migrated `mga` layer points at imports that don’t even exist here. If I want to insert agent logic after OCR, I can’t tell where the real seam is. I can find OCR models, text merge logic, and local-mode translation flow, but not a named stage boundary. So before I can extend anything, I have to reverse-engineer the monolith.”

#### DX findings

- Current docs optimize for the old host-layer framing, so contributor onboarding is misaligned with the actual runtime cut the user now wants.
- There is no named contract for post-OCR artifacts, which means “how do I extend this?” remains guesswork.
- Time to hello world for a future interceptor contributor is not “run a command,” it is “find the seam.” Right now that is too slow.

#### DX scorecard

```text
+====================================================================+
|              DX PLAN REVIEW — SCORECARD                            |
+====================================================================+
| Dimension            | Score | Notes                               |
|----------------------|-------|-------------------------------------|
| Getting Started      | 4/10  | README thesis mismatches runtime goal |
| API/CLI/SDK          | 3/10  | No real seam contract yet             |
| Error Messages       | 5/10  | Some runtime logging exists           |
| Documentation        | 4/10  | Design intent drifted from user thesis|
| Upgrade Path         | 3/10  | No staged seam migration story        |
| Dev Environment      | 6/10  | Existing runtime is runnable          |
| Community            | 5/10  | OSS repo, but maintainer path unclear |
| DX Measurement       | 4/10  | Smoke and benchmark path not aligned  |
+====================================================================+
```

### Decision Audit Trail

1. Auto-decided: reject old “external-core host layer” thesis as the primary frame for this round.
2. Auto-decided: use the user-confirmed “intention-driven pipeline interceptor” thesis.
3. Auto-decided: choose contract-first stage split as the preferred architecture cut.
4. Auto-decided: skip design review because there is no real UI scope.
5. Auto-decided: prioritize seam contract, reorder stage, and smoke validation over package/README-first work.

### Cross-Phase Themes

- The plan’s current north star is stale.
- The repo’s real leverage this round is a runtime seam after OCR.
- New text reordering is not a side feature; it is the first reason the seam must exist.
- `mga` benchmark/artifact work still has value, but now as validation infrastructure, not as the primary product definition.

### Deferred To TODOS.md

- memory/wiki write-back after the seam is stable
- deeper reasoning injection beyond the first seam
- broader contributor-facing CLI cleanup after the staged runtime exists

### Revised Commit Sequence

1. `docs: rewrite branch design around OCR-post interceptor seam`
2. `refactor: split runtime into explicit OCR reorder translate render stages`
3. `feat: add post-OCR contract and text reorder stage`
4. `test: add seam fixtures and staged smoke coverage`
5. `docs: realign README and contributor docs around staged runtime`
6. `feat: reattach benchmark and artifact tooling to staged runtime contracts`

### Completion Summary

```text
+====================================================================+
|            MEGA PLAN REVIEW — COMPLETION SUMMARY                   |
+====================================================================+
| Mode selected        | SELECTIVE / thesis-correction               |
| System Audit         | current plan optimized for stale thesis     |
| Step 0               | reframed around OCR-post interceptor seam   |
| Section 1  (Arch)    | 1 major architectural redirection           |
| Section 2  (Errors)  | 3 critical seam failure modes               |
| Section 3  (Security)| 1 contract hygiene concern                  |
| Section 4  (Data/UX) | seam and reorder edge cases identified      |
| Section 5  (Quality) | stale host-layer code path flagged          |
| Section 6  (Tests)   | diagram produced, multiple gaps             |
| Section 7  (Perf)    | secondary concern this round                |
| Section 8  (Observ)  | contract logging and artifacts needed       |
| Section 9  (Deploy)  | smoke path required before rollout claims   |
| Section 10 (Future)  | reversibility: 3/5                          |
| Section 11 (Design)  | SKIPPED (no UI scope)                      |
+--------------------------------------------------------------------+
| NOT in scope         | written                                     |
| What already exists  | written                                     |
| Dream state delta    | written                                     |
| Error/rescue registry| written                                     |
| Failure modes        | written, critical gaps present              |
| TODOS.md updates     | deferred conceptually                       |
| Scope proposals      | reframed to staged runtime seam             |
| CEO plan             | replaced by branch design doc               |
| Outside voice        | degraded, codex unavailable                 |
| Lake Score           | favored complete seam over wrapper shortcut |
| Diagrams produced    | architecture, path, test diagram            |
| Unresolved decisions | 2                                            |
+====================================================================+
```

### Unresolved Decisions

1. Whether the post-OCR contract wraps current `TextBlock` or introduces a new structure.
2. Whether dictionary application should move before or after reorder under the new staged runtime.

## Phase 4: Final Approval Gate

### Plan Summary

The old plan is no longer the right plan for this branch. The correct this-round objective is:

- carve a stable seam immediately after OCR
- add a text reorder stage
- make agent orchestration possible at that seam
- keep the rest of the runtime flowing through explicit staged contracts

### Decisions Made: 5 total (5 auto-decided, 0 taste choices, 1 user challenge already resolved in conversation)

### User Challenges

- What the old plan said:
  make this repo the formal `mga` external-core host layer
- What both the live conversation and the review now recommend:
  make this round about an intention-driven OCR-post interceptor seam instead
- Why:
  the user’s clarified goal is architectural interception inside the runtime, not repo-front-door host consolidation
- What context we might be missing:
  there may still be organizational value in formal packaging work, but it is not the best primary slice for this round
- If we’re wrong, the cost is:
  we invest in seam refactors before repo identity cleanup, delaying a cleaner host-layer story

### Your Choices

- Accepted during prerequisite review:
  - use open-source / research framing
  - allow generalized web search
  - replace the old thesis with the intention-driven interceptor thesis
  - choose contract-first stage split

### Review Scores

- Strategy alignment: `8/10` after reframe, `3/10` before reframe
- Engineering clarity: `7/10` if the seam contract becomes explicit
- DX readiness: `4/10` until docs and smoke paths align with the new architecture

### Final Recommendation

Do not keep executing this branch as a host-layer migration checklist.

Replace the top half of `plan.md` with a seam-first refactor plan derived from the new design doc, then execute against:

1. runtime cut mapping
2. post-OCR contract
3. reorder stage
4. staged smoke tests
5. only then README / CLI / benchmark realignment
