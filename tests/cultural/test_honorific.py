"""Tests for mga.cultural.honorific — honorific compensation system."""

from mga.cultural.honorific import HonorificCompensator, HonorificLevel


def test_analyze_in_group_intimate():
    h = HonorificCompensator()
    level = h.analyze(
        speaker_profile={"status": "peer", "in_group": True},
        listener_profile={"status": "peer", "in_group": True},
        relationship={"familiarity": "intimate", "distance": "casual"},
    )
    assert level == HonorificLevel.DANNAI


def test_analyze_listener_senior():
    h = HonorificCompensator()
    level = h.analyze(
        speaker_profile={"status": "junior", "in_group": True},
        listener_profile={"status": "senior", "in_group": True},
        relationship={"familiarity": "acquaintance", "distance": "formal"},
    )
    assert level == HonorificLevel.SONKEIGO


def test_analyze_default_teineigo():
    h = HonorificCompensator()
    level = h.analyze(
        speaker_profile={"status": "peer", "in_group": True},
        listener_profile={"status": "peer", "in_group": False},
        relationship={"familiarity": "acquaintance", "distance": "neutral"},
    )
    assert level == HonorificLevel.TEINEIGO


def test_compensate_zh_sonkeigo():
    h = HonorificCompensator()
    result = h.compensate("你是谁", HonorificLevel.SONKEIGO, "zh-CN")
    assert result.startswith("您")


def test_compensate_zh_sonkeigo_request_style():
    h = HonorificCompensator()
    result = h.compensate("你来一下！", HonorificLevel.SONKEIGO, "zh-CN")
    assert result == "请您来一下。"


def test_compensate_zh_sonkeigo_statement_does_not_add_request_marker():
    h = HonorificCompensator()
    result = h.compensate("你是谁", HonorificLevel.SONKEIGO, "zh-CN")
    assert result == "您是谁"


def test_compensate_zh_kenjougo_humble_action():
    h = HonorificCompensator()
    result = h.compensate("我来处理。", HonorificLevel.KENJOUGO, "zh-CN")
    assert result == "让我来处理。"


def test_compensate_zh_kenjougo_plain_first_person():
    h = HonorificCompensator()
    result = h.compensate("我处理。", HonorificLevel.KENJOUGO, "zh-CN")
    assert result == "让我处理。"


def test_compensate_zh_dannai_plural_uses_in_group_pronoun():
    h = HonorificCompensator()
    result = h.compensate("你们走吧", HonorificLevel.DANNAI, "zh-CN")
    assert result == "咱们走吧"


def test_compensate_zh_dannai_singular_does_not_emit_template_slash():
    h = HonorificCompensator()
    result = h.compensate("你先走吧", HonorificLevel.DANNAI, "zh-CN")
    assert result == "你先走吧"
    assert "/" not in result


def test_compensate_en_tameguchi():
    h = HonorificCompensator()
    result = h.compensate("you are here", HonorificLevel.TAMEGUCHI, "en")
    assert result == "you are here"  # "you" -> "you" (same)


def test_compensate_no_match():
    h = HonorificCompensator()
    result = h.compensate("Hello world", HonorificLevel.TEINEIGO, "fr")
    assert result == "Hello world"  # unsupported lang, no change


def test_get_form_of_address_peer_zh():
    h = HonorificCompensator()
    addr = h.get_form_of_address("田中", "zh-CN", {"familiarity": "peer"})
    assert "田中" in addr
    assert "同学" in addr


def test_get_form_of_address_default():
    h = HonorificCompensator()
    addr = h.get_form_of_address("田中", "en", {"familiarity": "close"})
    assert addr == "田中"
