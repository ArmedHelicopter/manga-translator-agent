"""Post-E2E verification: 1:1 mapping, re-inpaint coverage, vision validation.

Run after the E2E completes. Checks structural invariants only (counts, region
mapping, inpaint_status). Visual residual-Japanese inspection is delegated to a
vision-capable model separately — pixel diff is an unreliable proxy.
"""
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

OUT = Path("data/output/test-pdf-10pages-reinpaint")
PAYLOAD = OUT / ".mga-payload"


def main():
    run = json.loads((OUT / "run.json").read_text(encoding="utf-8"))
    print(f"status: {run.get('status')}  errors: {run.get('error_count')}")
    print(f"stages: {run.get('stages_completed')}")
    print(f"translation_count: {run.get('translation_count')}")
    timings = run.get("stage_timings", {})
    print(f"render timing: {timings.get('render')}s  vision: {timings.get('vision')}s")

    # 1:1 mapping: exactly 10 output pages
    outputs = sorted(OUT.glob("page-0*.png"))
    print(f"\n=== 1:1 mapping ===")
    print(f"output pages: {len(outputs)} (expected 10)")
    for p in outputs:
        print(f"  {p.name}: {p.stat().st_size/1024:.0f}KB")

    # Per-page region/translation alignment + inpaint_status
    print(f"\n=== Per-page artifact + translation alignment ===")
    for i in range(10):
        art_f = PAYLOAD / f"artifact-{i:04d}.json"
        tr_f = PAYLOAD / f"translations-{i:04d}.json"
        if not art_f.exists():
            print(f"  page {i}: NO ARTIFACT")
            continue
        art = json.loads(art_f.read_text(encoding="utf-8"))
        regions = art.get("text_regions", [])
        inpaint_status = art.get("inpaint_status", "inpainted")
        tr_count = 0
        oob = 0
        if tr_f.exists():
            tr = json.loads(tr_f.read_text(encoding="utf-8"))
            trs = tr.get("translations", [])
            tr_count = len(trs)
            oob = sum(1 for t in trs if t.get("region_index", -1) >= len(regions))
        flag = " [OOB!]" if oob else ""
        print(f"  page {i}: {len(regions)} regions, {tr_count} translations, "
              f"status={inpaint_status}{flag}")

    # Host-side vision validation: any bubbles dropped?
    print(f"\n=== Vision bubble counts (host translations) ===")
    tdir = OUT / "translations"
    if tdir.exists():
        for i in range(10):
            tf = tdir / f"page_{i:04d}.json"
            if not tf.exists():
                continue
            data = json.loads(tf.read_text(encoding="utf-8"))
            bubbles = data.get("bubbles", [])
            region = sum(1 for b in bubbles if b.get("bubble_id", "").startswith("region-"))
            vision = sum(1 for b in bubbles if b.get("bubble_id", "").startswith("vision-"))
            if vision or region:
                print(f"  page_{i:04d}: {region} region, {vision} vision bubbles")

    # vision artifact warnings
    print(f"\n=== Vision stage status ===")
    # run.json doesn't carry artifacts; check provider_cascade_calls
    vc = [c for c in run.get("provider_cascade_calls", []) if c.get("stage") == "vision"]
    print(f"  vision provider calls: {len(vc)}")
    ve = run.get("provider_cascade_errors", [])
    vision_errs = [e for e in ve if e.get("stage") == "vision"]
    print(f"  vision provider errors: {len(vision_errs)}")


if __name__ == "__main__":
    main()
