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
