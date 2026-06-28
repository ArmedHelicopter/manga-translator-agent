# GOAL: Full-Cycle Audit → Fix → Test → Iterate → Document Sync for Pipeline Index-Shift Desync

## 0. Convergence Criteria (Success condition that terminates the goal)
All the following must be satisfied before the goal is considered done and the agent stops:
1. **Visual alignment verified**: Use native vision modality to compare all 10 rendered page images against the source axioms. Confirm:
   - Page_003 shows [two girls eating shaved ice] and is linked to its correct payload `artifact-0003.json`, not `artifact-0002.json` from Page_004.
   - Page_004 shows [white background table of contents containing "Chapter 32" / "CONTENTS"] with its correct payload.
   - No -1 shift exists; page-009 and page-010 use independent base plates, not the same one.
2. **End-to-end test suite passes**: All test cases defined in Phase 3 (TE-01 through TE-04) pass with 0 failures.
3. **Documentation synchronized**: After all tests pass, execute the `/neat-freak` skill and confirm its report shows all documents are aligned with the final source code and outputs, with no pending updates.

**Convergence loop rule**: If Phase 3 tests fail, return to Phase 2 to revise the source code (maximum 3 iterations). After each iteration, rerun the full Phase 3 suite. If convergence is not reached within 3 iterations, output a detailed blocking analysis and pause for human intervention.

---

## 1. System Axioms (Immutable Physical Facts)
Before any analysis or modification, inject the following axioms into the global context. They cannot be overridden.
* **Source.Page_003**: Visual semantics = [two girls eating shaved ice], text semantics = [pure image, zero dialogue].
* **Source.Page_004**: Visual semantics = [white background table of contents], text semantics = [contains "Chapter 32", "CONTENTS"].
* **Pipeline.Current_Anomaly**: A -1 shift exists. The system incorrectly renders the Payload of Page_004 (`artifact-0002.json`) onto the output pointer of `page-003.png`.
* **Pipeline.Tail_Anomaly**: Tail stack overflow. Outputs `page-009` and `page-010` share the same underlying storyboard base plate.
* **Source Supremacy**: When JSON Payload textual content conflicts with the physical source image, the **source image is always correct**. The JSON contract is considered contaminated; never distort the image interpretation to match JSON.

---

## 2. Execution Invariants (Mandatory Guardrails)

### 2.1 Global Invariants
* **[ANTI-HEURISTIC]**: Never use “file byte size comparison” or “white pixel ratio” to determine image content identity. Always use native Vision modality to read image semantics.
* **[ZERO REGRESSION]**: Any fix must not introduce new page shifts, payload losses, or base plate reuse.
* **[TRACEABILITY]**: Every source code change must record the exact file path, line number, and the logical difference before and after the change.

### 2.2 Phase-Level Permissions
* **Phase 0 & Phase 1**: **READ-ONLY**. No `--render`, `--inpaint`, or any compile command allowed. No `edit_file` or `replace` on source code.
* **Phase 2**: **WRITE ALLOWED**. The `mga/` source code and related configuration may be modified. Every change must be logged.
* **Phase 3**: **READ-ONLY** for source code (only revert to Phase 2 on test failure). Test execution, rendering, and comparison are allowed.
* **Phase 4**: Execute `/neat-freak`; no manual file modifications.

---

## 3. Agent Orchestration & Fan-out Strategy
Use sub-agents to parallelize independent work. Merge conclusions at the end of each phase.
- **Phase 0**: Spawn sub-agents to read all project documentation and experiment logs in parallel.
- **Phase 1**: Spawn Agent‑A for Task_1 (physical-to-payload mapping) and Agent‑B for Task_2 (iterator source audit) simultaneously.
- **Phase 2**: The main agent drafts a patch based on the root cause. Optionally spawn Agent‑C to verify static side-effects.
- **Phase 3**: Spawn Agent‑D to execute the full end-to-end test suite (using high concurrency and the specified models), while Agent‑E monitors logs and stack traces.
- **Phase 4**: Main agent invokes `/neat-freak`.

---

## 4. Sub-Tasks & Phases

### Phase 0: Pre-flight — Document and Log Ingestion (READ-ONLY)
The main agent must fan out sub-agents to read **all** project documentation and existing experiment logs before any analysis. This establishes the project background and known failure signatures.
- **Documents to read**: `README.md`, any files under `docs/` (e.g., architecture, pipeline design), configuration comments, and any other design notes.
- **Experiment logs to read**: The log file from the most recent pipeline run (e.g., `logs/pipeline_run.log`, `experiment.log`, or the latest timestamped log in `logs/`). Extract the mapping of page indices to payload JSONs, error stack traces, and the output directory path.
- Sub-agents must return a concise summary of the pipeline structure, the observed anomalies, and the expected correct mapping. This summary is injected into the global context before Phase 1.

---

### Phase 1: Audit and Root-Cause Location (READ-ONLY)

1. **Task_1: Map_Physical_to_Payload**
   * Traverse the original input directory and the most recent `payload/` directory.
   * Build a complete 10-page physical mapping table, verifying the alignment between `Image_Index` and `Payload_Index` for every page.

2. **Task_2: Audit_Iterator_Source**
   * Use `grep` or AST tools to locate the context assembler in the `mga/` source code that **zips or iterates over the input image sequence and the translation payload sequence**.
   * Inspect the logic for: mixing of 0‑based and 1‑based indexing, implicit `continue/drop` on “silent pages” that shifts the queue forward, or missing explicit `.sort()` causing OS-level ordering issues.

**Phase 1 completion standard**:
- Print a full Markdown audit table with the exact format:  
  `| Page ID | Source Naked-Eye Semantics | Mounted JSON Filename | JSON First 15 Chars Preview | Status (Aligned / Shifted) |`
- Output the root cause location in the format: `file_path : line_number -> specific code block causing the pointer misalignment.`
- **After meeting this standard, automatically proceed to Phase 2 patching. Do not ask for user permission.**

---

### Phase 2: Patching (WRITE ALLOWED)
- Based on the confirmed root cause from Phase 1, make minimal, explainable modifications to the `mga/` source code to eliminate the -1 shift and the tail reuse.
- After modification, output a **Patch Description** containing: changed file, line numbers, logic before, logic after, and why it resolves the shift.
- **Never** make speculative changes without a clear root cause. If the root cause is ambiguous, revert to Phase 1 for deeper auditing.

---

### Phase 3: End-to-End Testing with High Concurrency and Specific Models
The end-to-end test is defined as: **first parse the previous experiment log to understand the original incorrect mappings, then execute a fresh pipeline run using the patched code, with high concurrency and the specified models, and finally validate the outputs against the source axioms and the correct mapping derived from the log.**

**Procedure:**
1. **Parse the experiment log** (the same log read in Phase 0). Extract the recorded faulty mapping (page → payload JSON) and error signatures. Determine the expected correct mapping for all 10 pages.
2. **Execute the full pipeline** using the patched code. The command must explicitly set:
   - Vision model: `--vision-model icompify/minimax-m3`
   - Translate model: `--translate-model icompify/deepseek-v4-pro`
   - High concurrency: e.g., `--workers 8` or the equivalent flag to enable parallel processing.
   - API keys for these models are already configured in the local environment; do not ask for them.
3. **After the run finishes**, read the newly generated experiment log and compare it with the old log to confirm that previous error patterns have disappeared.
4. **Run the following test cases. All must pass.**

| Test Case ID | Method | Passing Standard |
|--------------|--------|------------------|
| TE‑01 | For each of the 10 rendered page images, use the Vision model (`icompify/minimax-m3`) concurrently (concurrency 8) to extract the depicted scene semantics. | The extracted semantics for each page match the Source Axioms defined in Section 1. |
| TE‑02 | Check the JSON filename and first 15 characters mounted to each page’s output metadata. | Aligned perfectly with the correct mapping table produced in Phase 1. No offset. |
| TE‑03 | Use the Vision model to compare the base plates of `page-009.png` and `page-010.png`. | The two base plates are visually distinct; no reuse. |
| TE‑04 | Scan the new full pipeline log for errors. | Zero `IndexError`, `KeyError`, stack overflow, or duplicate resource release entries. |

* If any test case fails, record the failure details, return to Phase 2 (patching) and iterate, up to 3 total repair cycles.
* After each code revision, rerun the complete Phase 3 suite.
* If all tests pass, proceed to Phase 4.

---

### Phase 4: Documentation Synchronization
- Execute the `/neat-freak` skill.
- Verify its output shows all documentation (README, pipeline descriptions, configuration comments) is consistent with the final, patched source code and the corrected output.
- If `/neat-freak` reports remaining inconsistencies, follow its instructions to resolve them, then re-run until synchronization is complete.

---

## 5. Final Definition of Done
When Phase 3 passes completely and `/neat-freak` confirms full documentation sync, the main agent prints:
===== GOAL CONVERGED =====

Index-shift desync eliminated.

End-to-end tests passed: TE-01, TE-02, TE-03, TE-04.

Documentation synchronized via /neat-freak.
===== EXECUTION COMPLETE =====

text

All sub-agents are then stopped and the goal exits.