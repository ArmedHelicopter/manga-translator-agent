"""Page-level footnote compilation service.

Collects, deduplicates, and enhances footnotes from bubble translations
into a unified page-level footnote section.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mga.models.page import Page, PageFootnote
    from mga.models.translation import FootnoteEntry, TranslationCandidate


# ── Cultural Reference Database ───────────────────────────────────────────────

# Known cultural terms that need detailed explanations
CULTURAL_REFERENCES: dict[str, dict[str, str]] = {
    # Drinks & Food
    "ハイボール": {
        "type": "cultural",
        "translation": "高球（威士忌苏打）",
        "explanation": "Highball，日式鸡尾酒，通常指威士忌加苏打水加冰，口感清爽",
    },
    "烏龍茶": {
        "type": "cultural",
        "translation": "乌龙茶",
        "explanation": "半发酵茶，流行于日本餐厅免费提供",
    },
    "お嬢様": {
        "type": "cultural",
        "translation": "大小姐",
        "explanation": "对富裕家庭年轻女性的尊称，带有敬语和等级感",
    },
    "障子": {
        "type": "cultural",
        "translation": "障子/纸拉门",
        "explanation": "日式推拉门，以木框和半透明纸制成，用于分隔房间",
    },
    "お盆": {
        "type": "cultural",
        "translation": "盂兰盆节",
        "explanation": "日本传统节日，祭祀祖先，通常在8月中旬",
    },
    "初詣": {
        "type": "cultural",
        "translation": "新年参拜",
        "explanation": "新年首次去神社或寺院参拜祈福",
    },
    "七夕": {
        "type": "cultural",
        "translation": "七夕节",
        "explanation": "日本传统节日，在竹子上许愿，类似中国七夕",
    },
    "居酒屋": {
        "type": "cultural",
        "translation": "居酒屋",
        "explanation": "日本传统小酒馆，提供酒类和简单料理",
    },
    "銭湯": {
        "type": "cultural",
        "translation": "公共浴池",
        "explanation": "日本传统公共浴池，去泡澡是日常社交活动",
    },
    "お寺": {
        "type": "cultural",
        "translation": "寺庙",
        "explanation": "佛教寺院，与神社不同，用于佛教祭祀",
    },
    "神社": {
        "type": "cultural",
        "translation": "神社",
        "explanation": "神道信仰场所，用于祭祀神灵和祈福",
    },
    "巫女": {
        "type": "cultural",
        "translation": "巫女",
        "explanation": "神社中辅助祭祀的未婚女性，穿着传统白衣红袴",
    },
    "陰陽師": {
        "type": "cultural",
        "translation": "阴阳师",
        "explanation": "古代日本官职，擅长天文、历法、占卜和咒术",
    },
    "武士": {
        "type": "cultural",
        "translation": "武士",
        "explanation": "日本古代军事阶层，效忠主君，讲究武士道精神",
    },
    "侍": {
        "type": "cultural",
        "translation": "侍/武士",
        "explanation": "武士的日语说法，体现日本传统武家文化",
    },
    "忍者": {
        "type": "cultural",
        "translation": "忍者",
        "explanation": "日本古代间谍和刺客，擅长隐匿、忍术",
    },
    "忍術": {
        "type": "cultural",
        "translation": "忍术",
        "explanation": "忍者的技能，包括隐匿、伪装、投掷暗器等",
    },
    "刀": {
        "type": "cultural",
        "translation": "刀/武士刀",
        "explanation": "日本传统武器，象征武士身份",
    },
    "桜": {
        "type": "cultural",
        "translation": "樱花",
        "explanation": "日本国花，象征武士短暂而绚烂的生命观",
    },
    "花見": {
        "type": "cultural",
        "translation": "赏花",
        "explanation": "观赏樱花的日本传统习俗，春天重要的社交活动",
    },
    "敬語": {
        "type": "cultural",
        "translation": "敬语",
        "explanation": "日语中表示尊敬的语法体系，分为尊敬语、谦让语、丁重语",
    },
    "挨拶": {
        "type": "cultural",
        "translation": "问候/寒暄",
        "explanation": "日本社会中重要的礼节性交流方式",
    },
    "お握り": {
        "type": "cultural",
        "translation": "饭团",
        "explanation": "日本传统食物，用米饭包裹配料捏成三角形",
    },
    "おにぎり": {
        "type": "cultural",
        "translation": "饭团",
        "explanation": "日语饭团说法，传统便携食物",
    },
    "布団": {
        "type": "cultural",
        "translation": "被褥",
        "explanation": "日本传统卧具，包括铺在地板上的褥子和被子",
    },
    "畳": {
        "type": "cultural",
        "translation": "榻榻米",
        "explanation": "日本传统地板材料，用蔺草编制，房间大小以叠计算",
    },
    "浴衣": {
        "type": "cultural",
        "translation": "浴衣",
        "explanation": "日本传统夏季和服，用于温泉浴场和祭典",
    },
    "着物": {
        "type": "cultural",
        "translation": "和服",
        "explanation": "日本传统服装，穿法复杂，与浴衣不同",
    },
    "正月": {
        "type": "cultural",
        "translation": "新年/正月",
        "explanation": "日本最重要的节日，新年期间祭祀祖先、走亲访友",
    },
    "御守": {
        "type": "cultural",
        "translation": "护身符",
        "explanation": "神社出售的吉祥物，象征神灵保佑",
    },
    "お守り": {
        "type": "cultural",
        "translation": "护身符",
        "explanation": "神社出售的吉祥物，象征神灵保佑",
    },
    "賽銭": {
        "type": "cultural",
        "translation": "香钱",
        "explanation": "参拜时投入赛钱箱的硬币，表示对神明的供奉",
    },
    "おみくじ": {
        "type": "cultural",
        "translation": "抽签",
        "explanation": "神社的占卜活动，通过抽签了解运势",
    },
    "占術": {
        "type": "cultural",
        "translation": "占卜术",
        "explanation": "预测未来的技艺，包括四柱推命、占星等",
    },
    "风水": {
        "type": "cultural",
        "translation": "风水",
        "explanation": "源自中国的环境能量学，影响建筑和布局",
    },
    "開運": {
        "type": "cultural",
        "translation": "开运",
        "explanation": "通过某些方法招来好运",
    },
}

# Fictional/game terms that need explanation
FICTIONAL_REFERENCES: dict[str, dict[str, str]] = {
    "召喚": {
        "type": "fictional",
        "translation": "召唤",
        "explanation": "从异世界或虚空召唤生物/力量的魔法",
    },
    "魔法": {
        "type": "fictional",
        "translation": "魔法",
        "explanation": "虚构世界中操控超自然力量的技艺",
    },
    "スキル": {
        "type": "fictional",
        "translation": "技能",
        "explanation": "游戏或奇幻作品中角色拥有的特殊能力",
    },
    "アバター": {
        "type": "fictional",
        "translation": "化身/角色",
        "explanation": "游戏中玩家控制的虚拟角色，或网络身份",
    },
    "パーティ": {
        "type": "fictional",
        "translation": "队伍/组队",
        "explanation": "RPG游戏中多人协作的战斗单位",
    },
    "レベル": {
        "type": "fictional",
        "translation": "等级",
        "explanation": "游戏中角色或能力的等级数值",
    },
    "ステータス": {
        "type": "fictional",
        "translation": "状态/属性",
        "explanation": "游戏中角色的能力数值面板",
    },
    "経験値": {
        "type": "fictional",
        "translation": "经验值",
        "explanation": "游戏中角色升级所需的数值",
    },
    "アイテム": {
        "type": "fictional",
        "translation": "道具",
        "explanation": "游戏中使用的物品",
    },
    "武器": {
        "type": "fictional",
        "translation": "武器",
        "explanation": "战斗中使用的装备",
    },
    "防具": {
        "type": "fictional",
        "translation": "防具",
        "explanation": "防御用的装备",
    },
    "回復": {
        "type": "fictional",
        "translation": "恢复",
        "explanation": "恢复生命值或魔法值",
    },
    "MP": {
        "type": "fictional",
        "translation": "魔法值",
        "explanation": "Magic Point，使用魔法所需的精神力量",
    },
    "HP": {
        "type": "fictional",
        "translation": "生命值",
        "explanation": "Hit Point，生命力的数值表示",
    },
    "覚醒": {
        "type": "fictional",
        "translation": "觉醒",
        "explanation": "角色突破极限，获得新能力",
    },
    "転生": {
        "type": "fictional",
        "translation": "转生",
        "explanation": "死后投胎到另一个世界，是轻小说常见题材",
    },
    "異世界": {
        "type": "fictional",
        "translation": "异世界",
        "explanation": "与现实不同的虚构世界，轻小说常见设定",
    },
    "魔王": {
        "type": "fictional",
        "translation": "魔王",
        "explanation": "强大的邪恶存在，通常是故事的反派或最终boss",
    },
    "勇者": {
        "type": "fictional",
        "translation": "勇者",
        "explanation": "被选中对抗魔王的英雄",
    },
    "職業": {
        "type": "fictional",
        "translation": "职业",
        "explanation": "游戏中角色的身份，如战士、法师",
    },
}

# Combined database for lookup
ALL_CULTURAL_DB = {**CULTURAL_REFERENCES, **FICTIONAL_REFERENCES}


# ── Katakana Detection ────────────────────────────────────────────────────────

KATAKANA_PATTERN = re.compile(r"[ァ-ヺー]{2,}")
KANJI_PATTERN = re.compile(r"[一-鿿]+")


@dataclass
class PageFootnoteService:
    """Service for compiling page-level footnotes from bubble translations."""

    _seen_terms: dict[str, int] = field(default_factory=dict)  # term -> first bubble index

    def compile_page_footnotes(
        self,
        bubbles: list,
        translations: list[TranslationCandidate],
        page_context: str = "",
    ) -> list[PageFootnote]:
        """Compile all footnotes from bubble translations into a unified page list.

        Args:
            bubbles: List of Bubble objects (to get source text and bubble_id)
            translations: List of TranslationCandidate objects (with footnotes)
            page_context: Optional page-level context for better explanations

        Returns:
            List of PageFootnote objects, deduplicated and ordered
        """
        from mga.models.page import PageFootnote

        self._seen_terms.clear()
        page_footnotes: list[PageFootnote] = []
        footnote_index = 1

        for bubble, translation in zip(bubbles, translations):
            source_text = getattr(bubble, "source_text", "") or ""
            bubble_id = getattr(bubble, "bubble_id", "")

            for fn in translation.footnotes:
                if not fn.original:
                    continue

                # Check for duplicates
                term_key = fn.original.lower()
                if term_key in self._seen_terms:
                    continue  # Skip duplicate

                self._seen_terms[term_key] = footnote_index

                # Build explanation
                explanation = self._build_explanation(
                    term=fn.original,
                    fn_type=fn.type,
                    existing_explanation=fn.explanation,
                    source_text=source_text,
                    page_context=page_context,
                )

                page_footnotes.append(PageFootnote(
                    index=footnote_index,
                    term=fn.original,
                    translation=fn.translation or "见正文",
                    explanation=explanation,
                    type=fn.type,
                    source_bubble_id=bubble_id,
                ))
                footnote_index += 1

        return page_footnotes

    def _build_explanation(
        self,
        term: str,
        fn_type: str,
        existing_explanation: str | None,
        source_text: str,
        page_context: str,
    ) -> str:
        """Build or enhance explanation for a footnote.

        Priority:
        1. Existing explanation from LLM
        2. Database lookup (cultural/fictional references)
        3. Auto-generated from term type
        """
        # Use existing explanation if provided
        if existing_explanation:
            return existing_explanation

        # Check cultural database
        if term in ALL_CULTURAL_DB:
            return ALL_CULTURAL_DB[term]["explanation"]

        # Check partial matches in database
        for db_term, info in ALL_CULTURAL_DB.items():
            if db_term in term or term in db_term:
                return info["explanation"]

        # Auto-generate based on type
        if fn_type == "loanword":
            return self._explain_loanword(term, source_text)
        elif fn_type == "coined":
            return self._explain_coined(term, source_text)
        elif fn_type == "cultural":
            return self._explain_cultural(term, source_text)
        elif fn_type == "fictional":
            return self._explain_fictional(term, source_text)
        elif fn_type == "sfx":
            return self._explain_sfx(term, source_text)

        return f"源自日语的词汇"

    def _explain_loanword(self, term: str, source_text: str) -> str:
        """Generate explanation for katakana loanwords."""
        # Check if it's a common English loanword
        katakana_words = KATAKANA_PATTERN.findall(term)
        if katakana_words:
            # Try to identify the source word
            return f"片假名外来语，音译自外语"
        return f"日语片假名词汇"

    def _explain_coined(self, term: str, source_text: str) -> str:
        """Generate explanation for coined/author-created terms."""
        kanji_parts = KANJI_PATTERN.findall(term)
        if kanji_parts:
            return f"作者自创词汇，组合了{''.join(kanji_parts)}等汉字"
        return f"作者自创的虚构词汇"

    def _explain_cultural(self, term: str, source_text: str) -> str:
        """Generate explanation for cultural terms."""
        return f"日本文化特有概念，详见正文语境"

    def _explain_fictional(self, term: str, source_text: str) -> str:
        """Generate explanation for fictional/game terms."""
        return f"作品设定中的虚构概念"

    def _explain_sfx(self, term: str, source_text: str) -> str:
        """Generate explanation for sound effects."""
        return f"拟声词/音效，模拟声音效果"


# ── Singleton ─────────────────────────────────────────────────────────────────

_page_footnote_service: PageFootnoteService | None = None


def get_page_footnote_service() -> PageFootnoteService:
    """Get singleton PageFootnoteService instance."""
    global _page_footnote_service
    if _page_footnote_service is None:
        _page_footnote_service = PageFootnoteService()
    return _page_footnote_service


# ── Footnote Detection in Source Text ────────────────────────────────────────

def detect_footnote_terms(source_text: str) -> list[tuple[str, str]]:
    """Detect terms in source text that should have footnotes.

    Returns:
        List of (term, suggested_type) tuples
    """
    detected: list[tuple[str, str]] = []

    # Detect katakana loanwords
    for match in KATAKANA_PATTERN.finditer(source_text):
        term = match.group()
        if len(term) >= 2:
            # Check if it's in our cultural database
            if term in ALL_CULTURAL_DB:
                detected.append((term, ALL_CULTURAL_DB[term]["type"]))
            elif _is_loanword(term):
                detected.append((term, "loanword"))

    # Detect known cultural terms (kanji)
    for term, info in ALL_CULTURAL_DB.items():
        if term in source_text and KANJI_PATTERN.match(term):
            detected.append((term, info["type"]))

    return detected


def _is_loanword(term: str) -> bool:
    """Check if a katakana term is likely a loanword."""
    # Common patterns suggesting English loanwords
    loanword_indicators = [
        "カフェ", "コーヒー", "テレビ", "パソコン", "スマホ",
        "テレビ", "ラジオ", "ホテル", "メール", "インターネット",
        "ゲーム", "アニメ", "マンガ", "ドラマ", "スタジオ",
    ]
    return term in loanword_indicators or len(term) >= 4