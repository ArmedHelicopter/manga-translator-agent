from __future__ import annotations

import json
import shutil
import os
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
INTERNAL_DIR = Path(os.getenv("MTA_INTERNAL_DIR", ROOT / "data" / "runs" / "external" / "smoke_internal"))
EXTERNAL_DIR = Path(os.getenv("MTA_EXTERNAL_DIR", ROOT / "data" / "runs" / "external" / "smoke_external"))
REVIEW_DIR = Path(os.getenv("MTA_REVIEW_DIR", ROOT / "data" / "reviews" / "external_smoke_review"))


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_artifact(base_dir: Path, artifact: str) -> Path:
    return (base_dir / artifact).resolve()


def _parse_external_saved_text(path: Path) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    current_region: dict[str, str] | None = None

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue

        if stripped.startswith("[") and stripped.endswith("]"):
            if current is not None:
                if current_region is not None:
                    current["regions"].append(current_region)
                blocks.append(current)
            current = {"image_path": stripped[1:-1], "regions": []}
            current_region = None
            continue

        if current is None:
            continue

        if stripped.startswith("-- ") and stripped.endswith(" --"):
            if current_region is not None:
                current["regions"].append(current_region)
            current_region = {"text": "", "translation": ""}
            continue

        if current_region is None:
            continue

        if stripped.startswith("text:"):
            current_region["text"] = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("trans:"):
            current_region["translation"] = stripped.split(":", 1)[1].strip()

    if current is not None:
        if current_region is not None:
            current["regions"].append(current_region)
        blocks.append(current)
    return blocks


def _render_pairs(title: str, description: str, pairs: list[dict[str, str]]) -> str:
    lines = [f"## {title}", "", description, ""]
    if not pairs:
        lines.append("暂无可展示条目。")
        lines.append("")
        return "\n".join(lines)

    for index, pair in enumerate(pairs, start=1):
        source = (pair.get("source") or "").strip() or "(未单独保存原文)"
        translation = (pair.get("translation") or "").strip() or "(empty)"
        lines.extend(
            [
                f"### Unit {index}",
                "原文:",
                "```text",
                source,
                "```",
                "译文:",
                "```text",
                translation,
                "```",
                "",
            ]
        )
    return "\n".join(lines)


def _build_observations(
    *,
    structured_pairs: list[dict[str, str]],
    direct_pairs: list[dict[str, str]],
    external_pairs: list[dict[str, str]],
) -> list[str]:
    return [
        "## Evaluation Axes",
        "",
        "### source coverage",
        f"- `manga-translate-agent structured` 保留了 `{len(structured_pairs)}` 个单元，通常最接近可审查的气泡级保留。",
        "- `manga-translate-agent direct` 当前只稳定落盘译文单元，没有逐条原文 artifact，因此无法严格审计它到底识别到了哪些日文。",
        f"- `external manga-image-translator` 当前保留了 `{len(external_pairs)}` 个 OCR/区域单元，可直接核对其原文与译文，但其分段不一定与气泡结构同构。",
        "",
        "### translation fidelity",
        "- 重点看关键称呼、侮蔑词、关系语气和章节/旁白信息是否保留，而不是只看句子是否顺口。",
        "- 如果 `structured` 和 `external` 都保留了关键原文，而 `direct` 只有译文，则这页上 `direct` 的可审查性天然更弱。",
        "",
        "### unit alignment",
        f"- `manga-translate-agent structured` 本页拆成 `{len(structured_pairs)}` 个单元。",
        f"- `manga-translate-agent direct` 本页拆成 `{len(direct_pairs)}` 个单元。",
        f"- `external manga-image-translator` 本页拆成 `{len(external_pairs)}` 个单元。",
        "- 三者单元数不同并不等于谁更差，但会直接影响人工审校成本和后续嵌字对齐难度。",
        "",
    ]


def _build_external_page_map(output_dir: Path) -> tuple[dict[str, dict[str, Any]], dict[str, list[dict[str, str]]], dict[str, Any] | None]:
    normalized_path = output_dir / "external-baseline-text-normalized.json"
    saved_text_path = output_dir / "external-baseline-text.txt"
    summary_path = output_dir / "external-baseline-summary.json"

    normalized = _load_json(normalized_path) if normalized_path.exists() else []
    summary = _load_json(summary_path) if summary_path.exists() else None

    by_page_id = {
        item["page_id"]: item
        for item in normalized
        if item.get("page_id")
    }

    pairs_by_page_id: dict[str, list[dict[str, str]]] = {}
    if saved_text_path.exists():
        for block in _parse_external_saved_text(saved_text_path):
            resolved_path = str(Path(block["image_path"]).resolve())
            matched_page_id = None
            for page_id, item in by_page_id.items():
                if item.get("image_path") == resolved_path:
                    matched_page_id = page_id
                    break
            if matched_page_id is None:
                continue
            pairs_by_page_id[matched_page_id] = [
                {
                    "source": region.get("text", ""),
                    "translation": region.get("translation", ""),
                }
                for region in block.get("regions", [])
            ]

    return by_page_id, pairs_by_page_id, summary


def main() -> None:
    internal_report_path = INTERNAL_DIR / "benchmark" / "translation-report.json"
    external_report_path = EXTERNAL_DIR / "benchmark" / "external-translation-report.json"
    translation_report = _load_json(internal_report_path)
    external_report = _load_json(external_report_path)

    if REVIEW_DIR.exists():
        shutil.rmtree(REVIEW_DIR)
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)

    internal_by_page = {
        item["page_id"]: item
        for item in translation_report.get("comparisons", [])
    }
    external_by_page, external_pairs_by_page, external_summary = _build_external_page_map(EXTERNAL_DIR)

    overview_lines = [
        "# External Review Overview",
        "",
        "这份目录用于逐页横向比较：",
        "- `manga-translate-agent structured`",
        "- `manga-translate-agent direct`",
        "- `external manga-image-translator`",
        "",
        "## Pages",
        "",
    ]

    for comparison in external_report.get("comparisons", []):
        page_id = comparison["page_id"]
        image_path = Path(comparison["image_path"])
        page_dir = REVIEW_DIR / page_id
        page_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(image_path, page_dir / image_path.name)

        internal_comparison = internal_by_page.get(page_id)
        if internal_comparison is None:
            continue

        structured_payload = _load_json(
            _resolve_artifact(INTERNAL_DIR, internal_comparison["vision"]["structured"]["artifact"])
        )
        direct_payload = _load_json(
            _resolve_artifact(INTERNAL_DIR, internal_comparison["vision"]["direct"]["artifact"])
        )
        vision_payload = _load_json(INTERNAL_DIR / "benchmark" / "vision" / "structured" / f"{page_id}.json")

        (page_dir / "structured.joined.txt").write_text(
            internal_comparison["vision"]["structured"]["joined_text"] + "\n",
            encoding="utf-8",
        )
        (page_dir / "direct.joined.txt").write_text(
            internal_comparison["vision"]["direct"]["joined_text"] + "\n",
            encoding="utf-8",
        )
        (page_dir / "structured.full.json").write_text(
            json.dumps(structured_payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (page_dir / "direct.full.json").write_text(
            json.dumps(direct_payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        external_page = external_by_page.get(page_id)
        external_pairs = external_pairs_by_page.get(page_id, [])
        if external_page is not None:
            (page_dir / "external.joined.txt").write_text(
                (external_page.get("translated_text_joined") or "") + "\n",
                encoding="utf-8",
            )
            (page_dir / "external.full.json").write_text(
                json.dumps(external_page, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

        if external_summary is not None:
            (page_dir / "external.summary.json").write_text(
                json.dumps(external_summary, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            stderr = external_summary.get("stderr") or ""
            if stderr:
                (page_dir / "external.stderr.txt").write_text(stderr + "\n", encoding="utf-8")

        structured_by_id = {
            bubble["bubble_id"]: bubble.get("source_text", "")
            for bubble in vision_payload.get("bubbles", [])
        }
        structured_pairs = [
            {
                "source": structured_by_id.get(item.get("bubble_id", ""), ""),
                "translation": item.get("text", ""),
            }
            for item in structured_payload
        ]
        direct_pairs = [
            {
                "source": "",
                "translation": item.get("text", ""),
            }
            for item in direct_payload
        ]

        observations = _build_observations(
            structured_pairs=structured_pairs,
            direct_pairs=direct_pairs,
            external_pairs=external_pairs,
        )
        comparison_markdown = "\n".join(
            [
                f"# {page_id}",
                "",
                "这份对比的目的不是只看三段中文谁更顺，而是看 external OCR 管线和本仓库两种模式各自“看到了什么”以及“翻成了什么”。",
                "",
                f"- image: `{image_path.name}`",
                "",
                *observations,
                _render_pairs(
                    "manga-translate-agent structured",
                    "这是本仓库 `manga-translate-agent` 的结构化链路。原文来自本仓库保存的 `vision/structured/page-*.json`，译文来自结构化翻译结果。",
                    structured_pairs,
                ),
                _render_pairs(
                    "manga-translate-agent direct",
                    "这是本仓库 `manga-translate-agent` 的整页直翻链路。它和 structured 的区别是：不先显式抽取气泡/原文，而是直接让多模态模型看整页图给出翻译。当前只稳定保存了译文单元，没有把每条对应的源文本单独落盘。",
                    direct_pairs,
                ),
                _render_pairs(
                    "external manga-image-translator",
                    "这是外部开源项目 `manga-image-translator`。原文和译文来自它保存的 `external-baseline-text.txt`，本质上是文本区域/OCR 结果再送去翻译。",
                    external_pairs,
                ),
            ]
        )
        (page_dir / "comparison.md").write_text(
            comparison_markdown.strip() + "\n",
            encoding="utf-8",
        )

        review_summary = {
            "page_id": page_id,
            "image": image_path.name,
            "structured_joined_text": "structured.joined.txt",
            "direct_joined_text": "direct.joined.txt",
            "external_joined_text": "external.joined.txt" if (page_dir / "external.joined.txt").exists() else None,
            "external_summary": "external.summary.json" if (page_dir / "external.summary.json").exists() else None,
            "comparison_markdown": "comparison.md",
        }
        (page_dir / "review.json").write_text(
            json.dumps(review_summary, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        overview_lines.append(f"- [{page_id}](./{page_id}/comparison.md) : `{image_path.name}`")

    (REVIEW_DIR / "README.md").write_text("\n".join(overview_lines).strip() + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
