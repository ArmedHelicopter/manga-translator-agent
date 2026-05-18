# Test Fixtures

This directory stores file-based fixtures used by schema, stage, and end-to-end tests.

Recommended subdirectories:

- `images/source/`: original manga pages used as test inputs
- `images/expected/`: rendered output snapshots or cropped expectations
- `json/vision/`: golden page extraction JSON
- `json/translation/`: golden translation stage JSON
- `projects/`: small end-to-end sample projects

Fixture rules:

- Keep fixtures small and deterministic.
- Prefer anonymized or redistributable sample pages.
- Name files so they sort in reading order.
- Pair every golden JSON with a short note describing what it validates.
