from manager.dialogs.store_margin import PddProductMatchDialog


def test_scraped_title_change_is_not_recorded_as_spec_change():
    records = []
    dialog = type("Dialog", (), {
        "_record_product_operation": lambda self, *args: records.append(args),
    })()

    PddProductMatchDialog._record_scraped_link_changes(
        dialog, 7, "旧标题", "新标题", b"same", b"same",
        ((1, "spec"),), ((1, "spec"),), True,
    )

    assert len(records) == 1
    assert records[0][2] == "商品标题"
    assert records[0][-1] == "product_title"


def test_scraped_image_and_spec_changes_are_both_recorded():
    records = []
    dialog = type("Dialog", (), {
        "_record_product_operation": lambda self, *args: records.append(args),
    })()

    PddProductMatchDialog._record_scraped_link_changes(
        dialog, 7, "标题", "标题", b"old", b"new",
        ((1, "old"),), ((1, "new"),), True,
    )

    assert [record[2] for record in records] == ["主轮播图", "商品规格"]
