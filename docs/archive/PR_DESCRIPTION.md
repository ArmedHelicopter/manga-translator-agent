# Summary

This branch ships the `mga` host layer as the product entrypoint for the external-first manga translation workflow.

It adds:

- A Click-based `manga-translate` CLI with translate, benchmark, legacy, memory, profile, and terminology commands.
- A two-pass runtime bridge that exports OCR/render artifacts, runs the `mga` intelligence pipeline, and renders translated payloads.
- Structured artifacts, run summaries, translation reports, benchmark reports, and review surfaces.
- Provider routing with cascade support across OpenAI, Anthropic, Gemini, DeepSeek, OpenRouter, Ollama, vLLM, LM Studio, and llama.cpp.
- Memory/wiki/profile/graph infrastructure, cultural adaptation, QA proofreaders, learning engine modules, incremental translation, batch processing, and novel-mode coverage.

# Verification

- `pip install -e ".[dev]"`
- `python -m pytest tests -v`
  - Result: `609 passed, 1 skipped`
- `manga-translate --help`

# Notes

- Native Windows installs skip `pydensecrf` because the upstream source build requires Microsoft C++ Build Tools. The dependency remains active on non-Windows platforms and is only used by the legacy/runtime mask-refinement path.
- Real-world manga quality benchmarking and remote PR/merge actions are intentionally left for explicit follow-up.
