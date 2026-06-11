import numpy as np

from manga_translator.rendering import resize_regions_to_font_size, text_render
from manga_translator.rendering.text_render_eng import fit_font_size_to_ballon, seg_eng
from manga_translator.utils import TextBlock


def test_chinese_default_render_expands_short_translation_to_region():
    text_render.set_font("")
    region = TextBlock(
        [np.array([[0, 0], [180, 0], [180, 100], [0, 100]], dtype=np.int32)],
        texts=["は?"],
        font_size=18,
        translation="嗯？",
        target_lang="CHS",
        direction="h",
    )
    img = np.zeros((160, 240, 3), dtype=np.uint8)

    resize_regions_to_font_size(
        img,
        [region],
        font_size_fixed=None,
        font_size_offset=0,
        font_size_minimum=-1,
        hyphenate=True,
        line_spacing=0,
    )

    assert region.font_size >= 80


def test_manga2eng_font_fit_expands_short_translation_to_balloon_mask():
    text_render.set_font("")
    mask = np.zeros((110, 190), dtype=np.uint8)
    mask[5:105, 5:185] = 255
    fitted = fit_font_size_to_ballon(
        initial_font_size=18,
        min_font_size=12,
        max_font_size=180,
        ballon_mask=mask,
        words=seg_eng("HUH?"),
    )

    assert fitted >= 55
