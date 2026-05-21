"""Cultural problem classification for Japanese manga text."""

from __future__ import annotations

import re
from enum import Enum


class CulturalProblemType(Enum):
    """Categories of cultural translation challenges."""

    HONORIFIC = "honorific"
    COINED_TERM = "coined_term"
    CULTURAL_CONCEPT = "cultural_concept"
    ONOMATOPOEIA = "onomatopoeia"
    FICTIONAL_SCRIPT = "fictional_script"
    IDIOM = "idiom"
    FORM_OF_ADDRESS = "form_of_address"


_HONORIFIC_SUFFIXES = (
    "さん", "くん", "ちゃん", "様", "さま", "殿", "どの",
    "先生", "せんせい", "先輩", "せんぱい", "後輩", "こうはい",
)

_FORM_OF_ADDRESS_MARKERS = (
    "お兄さん", "お姉さん", "兄貴", "姉貴", "弟", "姉",
    "お父さん", "お母さん", "父上", "母上", "パパ", "ママ",
    "旦那", "奥さん", "坊主", "お嬢様",
)

_IDIOM_MARKERS = re.compile(
    r"(七転び八起き|猿も木から落ちる|虎の威|河童の川流れ|"
    r"出る杭は打たれる|釘を打つ|蛙の面に水|"
    r"石橋を叩いて渡る|焼け石に水|"
    r"はね|もの|こと|わけ|はず|まま|うち|あたり)",
)

_ONOMATOPOEIA_PATTERN = re.compile(
    r"[ァ-ヶー]{2,}|[ぁ-ん]{3,}|[一-龥]{2,}[ぁ-ヶー]|[ァ-ヶー]+[っ]|[っ][ァ-ヶー]+",
)

_FICTIONAL_SCRIPT_PATTERN = re.compile(
    r"[☀-➿⭐-⭕　-〿"
    r"\U0001F600-\U0001F64F\U0001F300-\U0001F5FF"
    r"\U0001F680-\U0001F6FF\U0001F900-\U0001F9FF]",
)

_COMMON_ONOMATOPOEIA = frozenset([
    "ドキドキ", "ゴロゴロ", "ニコニコ", "ジリジリ", "ガタガタ",
    "サクサク", "コロコロ", "キラキラ", "ユラユラ", "ボロボロ",
    "ガツガツ", "プクプク", "ゾクゾク", "ビクビク", "ゴツゴツ",
    "シクシク", "メチャクチャ", "バリバリ", "ペラペラ", "サラサラ",
    "フワフワ", "ドスドス", "ザワザワ", "ボフボフ", "ネバネバ",
])

_CULTURAL_CONCEPT_MARKERS = frozenset([
    "お盆", "初詣", "七夕", "節分", "お花見", "紅葉",
    "神社", "お寺", "巫女", "陰陽師", "武士", "侍",
    "忍者", "忍術", "刀", "桜", "花見", "盆踊り",
    "敬語", "挨拶", "居酒屋", "屋台", "銭湯",
])

_KANJI_IDIOM_PATTERN = re.compile(r"[一-鿿]{4,}")


def classify_problem(term_jp: str, context: str) -> list[CulturalProblemType]:
    """Classify a Japanese term into one or more cultural problem types.

    Args:
        term_jp: The Japanese source term or phrase.
        context: Surrounding text or page context for disambiguation.

    Returns:
        List of matching cultural problem types, ordered by likelihood.
    """
    problems: list[CulturalProblemType] = []
    term_stripped = term_jp.strip()

    if _is_honorific(term_stripped):
        problems.append(CulturalProblemType.HONORIFIC)

    if _is_form_of_address(term_stripped):
        problems.append(CulturalProblemType.FORM_OF_ADDRESS)

    if _is_onomatopoeia(term_stripped):
        problems.append(CulturalProblemType.ONOMATOPOEIA)

    if _is_cultural_concept(term_stripped):
        problems.append(CulturalProblemType.CULTURAL_CONCEPT)

    if _is_idiom(term_stripped):
        problems.append(CulturalProblemType.IDIOM)

    if _is_coined_term(term_stripped, context):
        problems.append(CulturalProblemType.COINED_TERM)

    if _is_fictional_script(term_stripped):
        problems.append(CulturalProblemType.FICTIONAL_SCRIPT)

    return problems


def _is_honorific(term: str) -> bool:
    return any(term.endswith(suffix) for suffix in _HONORIFIC_SUFFIXES)


def _is_form_of_address(term: str) -> bool:
    return any(marker in term for marker in _FORM_OF_ADDRESS_MARKERS)


def _is_onomatopoeia(term: str) -> bool:
    if term in _COMMON_ONOMATOPOEIA:
        return True
    return bool(_ONOMATOPOEIA_PATTERN.fullmatch(term))


def _is_cultural_concept(term: str) -> bool:
    return any(marker in term for marker in _CULTURAL_CONCEPT_MARKERS)


def _is_idiom(term: str) -> bool:
    if len(term) >= 4 and _KANJI_IDIOM_PATTERN.fullmatch(term):
        return True
    return bool(_IDIOM_MARKERS.search(term))


def _is_coined_term(term: str, context: str) -> bool:
    katakana_run = re.findall(r"[ァ-ヶー]{3,}", term)
    if katakana_run and context:
        lower_ctx = context.lower()
        return any(run.lower() not in lower_ctx.replace(term, "", 1) for run in katakana_run)
    return False


def _is_fictional_script(term: str) -> bool:
    return bool(_FICTIONAL_SCRIPT_PATTERN.search(term))
