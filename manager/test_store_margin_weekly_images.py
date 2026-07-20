from io import BytesIO

from PIL import Image

from manager.dialogs.store_margin import StoreMarginDialog, _next_store_image_slot, _should_clear_weekly_images


def test_weekly_images_have_no_fixed_slot_limit():
    assert _next_store_image_slot([]) == 0
    assert _next_store_image_slot([(0,), (5,), (23,)]) == 24


def test_weekly_images_clear_only_for_next_period():
    assert not _should_clear_weekly_images("", "2026-07-13", False)
    assert not _should_clear_weekly_images("2026-07-13", "2026-07-13", True)
    assert not _should_clear_weekly_images("2026-07-13", "2026-07-06", False)
    assert _should_clear_weekly_images("2026-07-13", "2026-07-20", False)


def test_weekly_export_keeps_original_pixels_but_uses_compact_display_size():
    source = BytesIO()
    Image.new("RGB", (320, 180), "white").save(source, "PNG")
    stream, width, height = StoreMarginDialog._high_res_export_image_stream(
        None, source.getvalue(), max_embed_size=None, max_display_width=96, max_display_height=96
    )
    assert Image.open(stream).size == (320, 180)
    assert (width, height) == (96, 54)
