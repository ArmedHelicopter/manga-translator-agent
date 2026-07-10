"""Tests for mga.cultural.coinage_detector — lifecycle for discovered coined terms."""

from mga.cultural.coinage_detector import CoinageCandidate, CoinageDetector


def _make_detector(tmp_path):
    """Create a CoinageDetector with a fresh project directory."""
    return CoinageDetector(project_dir=tmp_path)


def test_detect_katakana_coinage(tmp_path):
    """Katakana run like 'スーパーフォース' should be detected as coinage."""
    detector = _make_detector(tmp_path)
    # Space-separated so the tokenizer yields サーパーフォース as a standalone token
    candidates = detector.detect_from_text("彼は スーパーフォース を使った", page_id="p1")
    terms = [c.term_jp for c in candidates]
    assert "スーパーフォース" in terms
    found = next(c for c in candidates if c.term_jp == "スーパーフォース")
    assert found.count >= 1
    assert "katakana_coinage" in found.problem_types


def test_detect_mixed_script(tmp_path):
    """Mixed kanji+katakana token should be detected.

    The mixed_script regex matches kanji directly adjacent to katakana
    (e.g. 子ス in 硝子スーパー), not kanji+hiragana.
    """
    detector = _make_detector(tmp_path)
    # 硝子 (kanji) + スーパー (katakana) → mixed script match on "子ス"
    candidates = detector.detect_from_text("硝子スーパー 技術", page_id="p1")
    terms = [c.term_jp for c in candidates]
    assert "硝子スーパー" in terms
    found = next(c for c in candidates if c.term_jp == "硝子スーパー")
    assert "mixed_script" in found.problem_types


def test_detect_no_coinage(tmp_path):
    """Plain kanji like '太郎' should NOT be detected as coinage."""
    detector = _make_detector(tmp_path)
    candidates = detector.detect_from_text("太郎は学校へ行った", page_id="p1")
    terms = [c.term_jp for c in candidates]
    assert "太郎" not in terms


def test_detect_repeated_term(tmp_path):
    """Same term detected across multiple texts should increase count."""
    detector = _make_detector(tmp_path)
    # Space-separated so the tokenizer isolates the katakana token
    detector.detect_from_text("彼は スーパーフォース を使った", page_id="p1")
    detector.detect_from_text("敌は スーパーフォース に逃げた", page_id="p2")
    detector.detect_from_text("最後に スーパーフォース が現れた", page_id="p3")

    all_candidates = detector.get_all_candidates()
    assert "スーパーフォース" in all_candidates
    assert all_candidates["スーパーフォース"].count == 3
    assert len(all_candidates["スーパーフォース"].contexts) == 3


def test_get_proposals_min_count(tmp_path):
    """Only terms with count >= min_count should be returned."""
    detector = _make_detector(tmp_path)
    # One occurrence only — space-separated for clean tokenization
    detector.detect_from_text("ブルーフォース は強い", page_id="p1")
    # Two occurrences
    detector.detect_from_text("レッドフォース を使う", page_id="p1")
    detector.detect_from_text("レッドフォース が来た", page_id="p2")

    proposals = detector.get_proposals(min_count=2)
    proposal_terms = [p.term_jp for p in proposals]
    assert "レッドフォース" in proposal_terms
    assert "ブルーフォース" not in proposal_terms


def test_confirm(tmp_path):
    """Confirming a term should mark it confirmed and register in TerminologyDB."""
    detector = _make_detector(tmp_path)
    detector.detect_from_text("スーパーフォース", page_id="p1")

    result = detector.confirm("スーパーフォース", translation="Super Force", strategy="preserve")
    assert result is True

    # Check status updated
    candidate = detector.get_all_candidates()["スーパーフォース"]
    assert candidate.status == "confirmed"
    assert candidate.suggested_translation == "Super Force"
    assert candidate.suggested_strategy == "preserve"

    # Check TerminologyDB registration
    from mga.cultural.terminology_db import TerminologyDB

    db = TerminologyDB.load(tmp_path)
    term = db.lookup("スーパーフォース")
    assert term is not None
    assert term.confirmed is True
    assert term.term_target == "Super Force"


def test_reject(tmp_path):
    """Rejecting a term should mark it rejected."""
    detector = _make_detector(tmp_path)
    detector.detect_from_text("ファイアボール", page_id="p1")

    result = detector.reject("ファイアボール")
    assert result is True

    candidate = detector.get_all_candidates()["ファイアボール"]
    assert candidate.status == "rejected"


def test_confirm_nonexistent(tmp_path):
    """Confirming a term not in candidates should return False."""
    detector = _make_detector(tmp_path)
    result = detector.confirm("存在しない", translation="nonexistent", strategy="literal")
    assert result is False
