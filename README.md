# Manga Translate Agent

`mga` is an external-first manga translation host: it uses `manga-image-translator` as the runtime core and adds orchestration, artifact normalization, benchmarking, review workflows, and future intelligence-layer features on top.

This repository is the new `mga` main repo. The external runtime remains the execution core; `mga` is the host layer that makes runs inspectable, comparable, and extensible.

## Architecture

```text
┌──────────────────────────────────────────────┐
│ mga intelligence layer                       │
│ character consistency · QA · memory/wiki    │
├──────────────────────────────────────────────┤
│ mga orchestration layer                      │
│ artifacts · benchmark · review · config     │
├──────────────────────────────────────────────┤
│ external runtime core                        │
│ detection · OCR · inpainting · rendering    │
│ provided by manga-image-translator          │
└──────────────────────────────────────────────┘
```

## Current Repo Status

- `manga_translator/` is still the upstream external runtime codebase.
- `mga/` is the emerging host-layer package for artifact, benchmark, config, and runtime-bridge logic.
- `docs/PRD.md`, [docs/SPEC.md](/home/exusiai/_dev/manga-translator-agent/docs/SPEC.md), `docs/analysis/`, and `docs/research/` have already been migrated into this repo.
- Phase 1 is still in progress: the host-layer package exists, but the formal `translate`, `benchmark-external`, and `review` CLI surface is not fully wired yet.

## Package Layout

```text
mga/
├── artifacts/       # stable artifact persistence
├── benchmark/       # report generation and external benchmark workflows
├── cli/             # future formal entrypoints
├── config/          # mga -> external runtime config bridge
├── memory/          # future memory/wiki layer
├── qa/              # future QA evidence layer
├── review/          # future review entrypoints
└── runtime_bridge/  # external runtime invocation and normalization
```

## Planned Default Entrypoints

The repository is converging on these top-level host commands:

- `translate`
- `benchmark-external`
- `review`
- `legacy` or `research` for non-productized experiments

Those commands are part of the active migration plan in [plan.md](/home/exusiai/_dev/manga-translator-agent/plan.md:1). The package structure in this repo is being aligned to support them, but this README intentionally does not claim they are complete today.

## Stable Host-Layer Responsibilities

`mga` is responsible for:

- resolving provider and host config before runtime launch
- invoking the external runtime in a controlled way
- normalizing runtime outputs into stable artifacts
- generating benchmark and review inputs
- keeping future intelligence features out of the external runtime core

The external runtime remains responsible for:

- page/image translation execution
- detection, OCR, inpainting, and rendering internals
- runtime-specific CLI/config behavior

## Artifact Contract

The Phase 1 target contract for a translated run is:

```text
output/
├── manifest.json
├── external-baseline-summary.json
├── external-baseline-text.txt
├── external-baseline-text-normalized.json
└── run.json
```

If the external runtime emits rendered images, the output summary should also record them explicitly.

## Benchmark And Review

Benchmarking is not a side script in this repo; it is one of the core `mga` capabilities.

The immediate migration priority is:

- external translation benchmark
- same-page review assembly
- multi-page review assembly
- external text normalization

The migrated benchmark code lives under [mga/benchmark](/home/exusiai/_dev/manga-translator-agent/mga/benchmark) and related tests live under [tests/benchmark](/home/exusiai/_dev/manga-translator-agent/tests/benchmark).

## Legacy And Research Assets

This repository still carries a large amount of upstream runtime code and legacy experimentation material:

- upstream runtime implementation in `manga_translator/`
- migration and product docs in `docs/`
- review assembly scripts in `scripts/`
- legacy and exploratory tests under `test/`

For this migration round, those assets remain available, but the target product path is the external-core host architecture described above.

## Tests

The new host-layer test layout is:

- [tests/runtime](/home/exusiai/_dev/manga-translator-agent/tests/runtime) for runtime-bridge and smoke coverage
- [tests/benchmark](/home/exusiai/_dev/manga-translator-agent/tests/benchmark) for benchmark/report behavior
- [tests/fixtures](/home/exusiai/_dev/manga-translator-agent/tests/fixtures) for shared file fixtures

See [tests/README.md](/home/exusiai/_dev/manga-translator-agent/tests/README.md) for the intended coverage split.

## Related Docs

- [docs/PRD.md](/home/exusiai/_dev/manga-translator-agent/docs/PRD.md)
- [docs/SPEC.md](/home/exusiai/_dev/manga-translator-agent/docs/SPEC.md)
- [docs/research/oss-landscape.md](/home/exusiai/_dev/manga-translator-agent/docs/research/oss-landscape.md)
- [docs/research/market-landscape.md](/home/exusiai/_dev/manga-translator-agent/docs/research/market-landscape.md)
- [README_CN.md](/home/exusiai/_dev/manga-translator-agent/README_CN.md) for the upstream/runtime-oriented Chinese README that still needs migration

## Migration Notes

- `README.mga-draft.md` was the draft source for the repo identity rewrite and is now superseded by this front-door README.
- The old internal schema and pipeline shape are not being promoted as the new core contract.
- Memory/wiki, QA, and character-consistency systems should be reattached only after the host path is stable.
