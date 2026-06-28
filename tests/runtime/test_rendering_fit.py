import numpy as np

from manga_translator.rendering import resize_regions_to_font_size
from manga_translator.utils import TextBlock


def test_resize_regions_does_not_expand_target_polygon_for_long_vertical_text(monkeypatch) -> None:
    from manga_translator import rendering

    monkeypatch.setattr(
        rendering.text_render,
        "calc_vertical",
        lambda *args, **kwargs: (["一", "定", "和"], None),
    )
    img = np.full((500, 500, 3), 255, dtype=np.uint8)
    region = TextBlock(
        lines=[[[100, 100], [160, 100], [160, 420], [100, 420]]],
        texts=["きっと"],
        font_size=80,
        translation="一定和我一样呢",
        source_lang="ja",
        target_lang="CHS",
    )

    [dst_points] = resize_regions_to_font_size(
        img,
        [region],
        font_size_fixed=None,
        font_size_offset=0,
        font_size_minimum=8,
        hyphenate=True,
        line_spacing=None,
    )

    assert np.array_equal(dst_points, region.min_rect)
