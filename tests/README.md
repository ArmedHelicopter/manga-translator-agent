# Tests

This directory holds the new host-layer test suite for the `mga` migration.

Current intended split:

- `tests/runtime/`: smoke coverage for host preflight, runtime-bridge behavior, command assembly, and artifact persistence
- `tests/benchmark/`: benchmark normalization, reporting, and external comparison flows
- `tests/fixtures/`: shared file fixtures for runtime and benchmark tests

What belongs here versus `test/`:

- `tests/` is for the new `mga` host-layer architecture
- `test/` remains the legacy/upstream-style test area tied to the existing runtime codebase

Coverage expectations for this directory:

- runtime bridge tests should validate external runtime repo resolution, subprocess command construction, and stable output artifacts
- benchmark tests should validate extraction and translation reports, normalized external outputs, and benchmark run logs
- memory/wiki tests are not expected yet; that layer is still planned work

Fixture guidance:

- keep fixtures small and deterministic
- prefer redistributable sample pages
- name files in reading order
- store golden reports or JSON only when they protect a stable contract
