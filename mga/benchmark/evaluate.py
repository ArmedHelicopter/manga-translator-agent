"""Benchmark pipelines for extraction and translation."""

from __future__ import annotations

import json
import random
import shutil
import subprocess
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

from ..artifacts import ArtifactStore
from ..providers.base import LLMProvider
from ..models import Page, TranslationCandidate

DEFAULT_OCR_SPECS = ("tesseract_jpn", "tesseract_jpn_vert", "tesseract_jpn+eng")
DEFAULT_VISION_MODES = ("structured", "direct")


@dataclass
class OcrResult:
    page_id: str
    text: str
    raw_path: str
    line_count: int
    character_count: int
    ocr_spec: str


def _normalize_text(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.splitlines()).strip()


def _normalize_for_score(text: str) -> str:
    return "".join(text.split())


def _vision_page_metrics(page: Page) -> dict:
    bubble_texts = [bubble.source_text.strip() for bubble in page.bubbles if bubble.source_text.strip()]
    joined_text = "\n".join(bubble_texts)
    return {
        "bubble_count": len(page.bubbles),
        "non_empty_bubble_count": len(bubble_texts),
        "character_count": len(joined_text),
        "line_count": len([line for line in joined_text.splitlines() if line.strip()]),
        "joined_text": joined_text,
    }


def _translation_metrics(translations: list[TranslationCandidate]) -> dict:
    texts = [item.text.strip() for item in translations if item.text.strip()]
    joined_text = "\n".join(texts)
    return {
        "unit_count": len(translations),
        "non_empty_unit_count": len(texts),
        "character_count": len(joined_text),
        "line_count": len([line for line in joined_text.splitlines() if line.strip()]),
        "joined_text": joined_text,
    }


def select_sample_pages(
    pages: list[Page],
    *,
    max_pages: int,
    start_index: int = 0,
    sample_strategy: str = "window",
    seed: int = 42,
) -> list[Page]:
    """Select a subset of pages for benchmarking."""

    if max_pages <= 0 or len(pages) <= max_pages:
        return pages

    if sample_strategy == "window":
        safe_start = max(0, min(start_index, len(pages) - max_pages))
        return pages[safe_start:safe_start + max_pages]

    if sample_strategy == "random":
        rng = random.Random(seed)
        sampled = rng.sample(pages, max_pages)
        return sorted(sampled, key=lambda page: page.page_index)

    raise RuntimeError(f"Unsupported sample strategy: {sample_strategy}")


def _run_tesseract_ocr(
    image_path: Path,
    output_dir: Path,
    page_id: str,
    lang: str,
    spec_name: str,
) -> OcrResult:
    if shutil.which("tesseract") is None:
        raise RuntimeError("tesseract is not installed; OCR benchmark cannot run.")

    base = output_dir / spec_name / page_id
    base.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        ["tesseract", str(image_path), str(base), "-l", lang],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"Tesseract OCR failed for {image_path.name} with {spec_name}: "
            f"{completed.stderr.strip() or completed.stdout.strip()}"
        )

    txt_path = base.with_suffix(".txt")
    text = _normalize_text(txt_path.read_text(encoding="utf-8"))
    return OcrResult(
        page_id=page_id,
        text=text,
        raw_path=str(txt_path),
        line_count=len([line for line in text.splitlines() if line.strip()]),
        character_count=len(text),
        ocr_spec=spec_name,
    )


def _run_ocr_spec(image_path: Path, ocr_dir: Path, page_id: str, spec_name: str) -> OcrResult:
    if spec_name == "tesseract_jpn":
        return _run_tesseract_ocr(image_path, ocr_dir, page_id, "jpn", spec_name)
    if spec_name == "tesseract_jpn_vert":
        return _run_tesseract_ocr(image_path, ocr_dir, page_id, "jpn_vert", spec_name)
    if spec_name == "tesseract_jpn+eng":
        return _run_tesseract_ocr(image_path, ocr_dir, page_id, "jpn+eng", spec_name)
    raise RuntimeError(f"Unsupported OCR spec: {spec_name}")


def _safe_run_ocr_spec(image_path: Path, ocr_dir: Path, page_id: str, spec_name: str) -> tuple[OcrResult | None, str | None]:
    try:
        return _run_ocr_spec(image_path, ocr_dir, page_id, spec_name), None
    except RuntimeError as exc:
        return None, str(exc)


def _score_text(predicted_text: str, reference_text: str | None) -> dict | None:
    if not reference_text:
        return None

    predicted = _normalize_for_score(predicted_text)
    reference = _normalize_for_score(reference_text)
    if not reference:
        return None

    ratio = SequenceMatcher(a=predicted, b=reference).ratio()
    estimated_cer = 1.0 - ratio
    return {
        "reference_character_count": len(reference),
        "predicted_character_count": len(predicted),
        "similarity_ratio": round(ratio, 4),
        "estimated_character_error_rate": round(estimated_cer, 4),
    }


def _load_reference_annotations(annotations_path: Path | None) -> dict[str, dict]:
    if annotations_path is None or not annotations_path.exists():
        return {}
    payload = json.loads(annotations_path.read_text(encoding="utf-8"))
    return {item["page_id"]: item for item in payload.get("pages", [])}


def _write_annotation_template(template_path: Path, pages_payload: list[dict], instructions: dict) -> None:
    template_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "instructions": instructions,
        "pages": pages_payload,
    }
    template_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _aggregate_scores(score_map: dict[str, list[float]]) -> dict:
    aggregate = {}
    for name, values in score_map.items():
        aggregate[name] = {
            "scored_page_count": len(values),
            "average_estimated_character_error_rate": round(sum(values) / len(values), 4) if values else None,
        }
    return aggregate


def run_extraction_benchmark(
    *,
    pages: list[Page],
    provider: LLMProvider,
    store: ArtifactStore,
    ocr_specs: list[str],
    annotations_path: Path | None = None,
) -> dict:
    """Compare extracted source text from structured vision and OCR baselines."""

    benchmark_root = store.root / "benchmark"
    vision_dir = benchmark_root / "vision"
    ocr_dir = benchmark_root / "ocr"
    benchmark_root.mkdir(exist_ok=True)
    vision_dir.mkdir(exist_ok=True)
    ocr_dir.mkdir(exist_ok=True)

    references = _load_reference_annotations(annotations_path)
    comparisons: list[dict] = []
    aggregate_scores: dict[str, list[float]] = {"vision_structured": []}
    for spec_name in ocr_specs:
        aggregate_scores[spec_name] = []

    for page in pages:
        analyzed_page, _ = provider.vision_extract(page, store=store)
        vision_payload = analyzed_page.model_dump(mode="json")
        vision_path = vision_dir / "structured" / f"{page.page_id}.json"
        vision_path.parent.mkdir(parents=True, exist_ok=True)
        vision_path.write_text(
            json.dumps(vision_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        metrics = _vision_page_metrics(analyzed_page)
        reference_text = references.get(page.page_id, {}).get("reference_text")
        vision_score = _score_text(metrics["joined_text"], reference_text)
        if vision_score is not None:
            aggregate_scores["vision_structured"].append(vision_score["estimated_character_error_rate"])

        ocr_results = {}
        for spec_name in ocr_specs:
            result, error = _safe_run_ocr_spec(Path(page.image.path), ocr_dir, page.page_id, spec_name)
            if result is None:
                ocr_results[spec_name] = {
                    "line_count": None,
                    "character_count": None,
                    "joined_text": None,
                    "artifact": None,
                    "score": None,
                    "error": error,
                }
                continue

            score = _score_text(result.text, reference_text)
            if score is not None:
                aggregate_scores[spec_name].append(score["estimated_character_error_rate"])
            ocr_results[spec_name] = {
                "line_count": result.line_count,
                "character_count": result.character_count,
                "joined_text": result.text,
                "artifact": str(Path(result.raw_path).relative_to(store.root)),
                "score": score,
                "error": None,
            }

        comparisons.append(
            {
                "page_id": page.page_id,
                "image_path": page.image.path,
                "reference_text": reference_text,
                "vision_structured": {
                    "artifact": str(vision_path.relative_to(store.root)),
                    "bubble_count": metrics["bubble_count"],
                    "non_empty_bubble_count": metrics["non_empty_bubble_count"],
                    "line_count": metrics["line_count"],
                    "character_count": metrics["character_count"],
                    "joined_text": metrics["joined_text"],
                    "score": vision_score,
                },
                "ocr": ocr_results,
            }
        )

    template_path = benchmark_root / "annotations.extraction.template.json"
    _write_annotation_template(
        template_path,
        [
            {
                "page_id": item["page_id"],
                "image_path": item["image_path"],
                "reference_text": "",
                "notes": "",
            }
            for item in comparisons
        ],
        {
            "reference_text": "Fill in the exact Japanese source text you consider the gold transcription for each page.",
            "notes": "Optional human notes about OCR failure modes, bubble ordering, or ambiguous glyphs.",
        },
    )

    summary = {
        "page_count": len(comparisons),
        "ocr_specs": ocr_specs,
        "annotation_template": str(template_path.relative_to(store.root)),
        "aggregate": _aggregate_scores(aggregate_scores),
        "comparisons": comparisons,
    }
    store.write_json("benchmark/extraction-report.json", summary)
    return summary


def run_translation_benchmark(
    *,
    pages: list[Page],
    provider: LLMProvider,
    store: ArtifactStore,
    vision_modes: list[str],
    annotations_path: Path | None = None,
) -> dict:
    """Compare translated outputs across Vision-first translation modes."""

    benchmark_root = store.root / "benchmark"
    translation_dir = benchmark_root / "translation"
    translation_dir.mkdir(parents=True, exist_ok=True)

    references = _load_reference_annotations(annotations_path)
    comparisons: list[dict] = []
    aggregate_scores: dict[str, list[float]] = {}
    for mode in vision_modes:
        aggregate_scores[f"vision_{mode}"] = []

    for page in pages:
        reference_text = references.get(page.page_id, {}).get("reference_text")
        results = {}
        for mode in vision_modes:
            if mode == "structured":
                analyzed_page, _ = provider.vision_extract(page, store=store)
                utterances = [
                    {
                        "bubble_id": bubble.bubble_id,
                        "source_text": bubble.source_text,
                        "speaker": bubble.speaker_name or bubble.speaker_id,
                        "tone": bubble.tone,
                        "context_notes": bubble.notes,
                    }
                    for bubble in sorted(analyzed_page.bubbles, key=lambda item: item.reading_order)
                ]
                from ..models import Utterance  # local import to avoid cycle at module import time

                translations, _ = provider.translate(
                    analyzed_page,
                    [Utterance.model_validate(item) for item in utterances],
                    store=store,
                )
            elif mode == "direct":
                translations, _ = provider.direct_translate_page(page, store=store)
            else:
                raise RuntimeError(f"Unsupported vision mode: {mode}")

            metrics = _translation_metrics(translations)
            score = _score_text(metrics["joined_text"], reference_text)
            if score is not None:
                aggregate_scores[f"vision_{mode}"].append(score["estimated_character_error_rate"])
            out_path = translation_dir / mode / f"{page.page_id}.json"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(
                json.dumps([item.model_dump(mode="json") for item in translations], ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            results[mode] = {
                "artifact": str(out_path.relative_to(store.root)),
                "unit_count": metrics["unit_count"],
                "non_empty_unit_count": metrics["non_empty_unit_count"],
                "line_count": metrics["line_count"],
                "character_count": metrics["character_count"],
                "joined_text": metrics["joined_text"],
                "score": score,
            }

        comparisons.append(
            {
                "page_id": page.page_id,
                "image_path": page.image.path,
                "reference_text": reference_text,
                "vision": results,
            }
        )

    template_path = benchmark_root / "annotations.translation.template.json"
    _write_annotation_template(
        template_path,
        [
            {
                "page_id": item["page_id"],
                "image_path": item["image_path"],
                "reference_text": "",
                "notes": "",
            }
            for item in comparisons
        ],
        {
            "reference_text": "Fill in the gold Simplified Chinese translation you want to compare against for each page.",
            "notes": "Optional notes about phrasing choices, speaker tone, or omitted chapter markers.",
        },
    )

    summary = {
        "page_count": len(comparisons),
        "vision_modes": vision_modes,
        "annotation_template": str(template_path.relative_to(store.root)),
        "aggregate": _aggregate_scores(aggregate_scores),
        "comparisons": comparisons,
    }
    store.write_json("benchmark/translation-report.json", summary)
    return summary


def run_external_translation_benchmark(
    *,
    pages: list[Page],
    internal_translation_report: dict,
    external_pages: list[dict],
    store: ArtifactStore,
    annotations_path: Path | None = None,
    external_name: str = "manga_image_translator",
) -> dict:
    """Compare internal translation modes against an external page-level baseline."""

    benchmark_root = store.root / "benchmark"
    references = _load_reference_annotations(annotations_path)
    external_by_page = {
        item["page_id"]: item
        for item in external_pages
        if item.get("page_id")
    }

    aggregate_scores: dict[str, list[float]] = {
        "vision_structured": [],
        "vision_direct": [],
        f"external_{external_name}": [],
    }
    internal_comparisons = {
        item["page_id"]: item
        for item in internal_translation_report.get("comparisons", [])
    }
    comparisons: list[dict] = []

    for page in pages:
        reference_text = references.get(page.page_id, {}).get("reference_text")
        internal = internal_comparisons.get(page.page_id)
        if internal is None:
            continue

        vision_results = {}
        for mode, payload in internal.get("vision", {}).items():
            score = _score_text(payload["joined_text"], reference_text)
            if score is not None:
                aggregate_scores[f"vision_{mode}"].append(score["estimated_character_error_rate"])
            vision_results[mode] = {
                **payload,
                "score": score,
            }

        external_payload = external_by_page.get(page.page_id)
        external_result = None
        if external_payload is not None:
            score = _score_text(external_payload.get("translated_text_joined", ""), reference_text)
            if score is not None:
                aggregate_scores[f"external_{external_name}"].append(score["estimated_character_error_rate"])
            external_result = {
                "artifact": "external-baseline-text-normalized.json",
                "joined_text": external_payload.get("translated_text_joined", ""),
                "source_text_joined": external_payload.get("source_text_joined", ""),
                "character_count": len(external_payload.get("translated_text_joined", "")),
                "line_count": len(
                    [line for line in external_payload.get("translated_text_joined", "").splitlines() if line.strip()]
                ),
                "unit_count": external_payload.get("region_count", 0),
                "score": score,
            }

        comparisons.append(
            {
                "page_id": page.page_id,
                "image_path": page.image.path,
                "reference_text": reference_text,
                "vision": vision_results,
                "external": {
                    external_name: external_result,
                },
            }
        )

    summary = {
        "page_count": len(comparisons),
        "annotation_template": internal_translation_report.get("annotation_template"),
        "aggregate": _aggregate_scores(aggregate_scores),
        "comparisons": comparisons,
        "external_name": external_name,
    }
    store.write_json("benchmark/external-translation-report.json", summary)
    return summary
