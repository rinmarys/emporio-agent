from datetime import datetime
import logging

import pandas as pd
import pytest

from app.data_store import build_products, get_products, load_tables
from app.rules import UNKNOWN_AVAILABILITY, availability, order_status_pt, payment_method_pt, store_status


def product(name_part: str):
    rows = get_products()[get_products()["name"].str.contains(name_part, regex=False)]
    assert len(rows) == 1, f"expected one product matching {name_part!r}, got {len(rows)}"
    return rows.iloc[0]


def fake_tables(products_rows, promotions_rows):
    return {
        "products": pd.DataFrame(
            products_rows, columns=["product_id", "name", "category_id", "status", "stock_quantity"]
        ),
        "categories": pd.DataFrame([[1, "Guitarras"]], columns=["category_id", "name"]),
        "promotions": pd.DataFrame(
            promotions_rows,
            columns=["promotion_id", "product_id", "discount_percent", "description", "is_active"],
        ),
    }


@pytest.mark.parametrize(
    "name_part, expected",
    [
        ("Ibanez Bass 2X", "fora de linha"),  # discontinued with 13 in stock (D8-5)
        ("Kala KA-ABP-CTG Barítono", "em breve"),  # coming_soon with 2 in stock (D8-6)
        ("Giannini GF-3D", "indisponível no momento"),  # active, stock 0 (D8-7)
        ("Takamine GC5CE", "últimas unidades"),  # active, stock 3
        ("Takamine GD20", "disponível"),  # active, stock 5
    ],
)
def test_availability_labels_on_real_products(name_part, expected):
    assert product(name_part)["availability"] == expected


def test_status_wins_over_stock():
    assert availability("discontinued", 100) == "fora de linha"
    assert availability("coming_soon", 100) == "em breve"


@pytest.mark.parametrize("stock", [float("nan"), -1])
def test_untrustworthy_stock_is_never_shown_as_available(stock):
    assert availability("active", stock) == UNKNOWN_AVAILABILITY


def test_unknown_status_points_customer_to_team_and_logs(caplog):
    tables = fake_tables([[1, "Guitarra X", 1, "archived", 5]], [])
    with caplog.at_level(logging.WARNING):
        products = build_products(tables)
    assert products.iloc[0]["availability"] == UNKNOWN_AVAILABILITY
    assert "(67) 3321-4500" in UNKNOWN_AVAILABILITY
    assert "archived" in caplog.text


def test_text_in_stock_column_does_not_crash_the_load():
    tables = fake_tables([[1, "Guitarra X", 1, "active", 5], [2, "Guitarra Y", 1, "active", "abc"]], [])
    products = build_products(tables)
    assert products["availability"].tolist() == ["disponível", UNKNOWN_AVAILABILITY]


def test_multiple_active_promotions_are_kept_most_recent_first():
    tables = fake_tables(
        [[1, "Guitarra X", 1, "active", 5]],
        [[7, 1, 10, "Antiga", 1], [9, 1, 15, "Nova", 1], [8, 1, 30, "Inativa", 0]],
    )
    products = build_products(tables)
    assert len(products) == 1  # no duplicated product rows
    assert [p["description"] for p in products.iloc[0]["promotions"]] == ["Nova", "Antiga"]


def test_real_products_have_category_name_and_active_promotions_only():
    products = get_products()
    assert product("Takamine GD20")["category"] == "Violões"
    assert product("Takamine GD20")["promotions"] == []
    assert product("Kalani KAL-700T")["promotions"] == [
        {"promotion_id": 12, "description": "Oferta Especial", "discount_percent": 10}
    ]
    assert sum(len(p) for p in products["promotions"]) == 4  # only is_active == 1
    assert products["product_id"].is_unique


def test_csvs_are_loaded_once():
    assert load_tables() is load_tables()
    assert get_products() is get_products()


def test_pt_br_translations_cover_all_values_in_data():
    orders = load_tables()["orders"]
    for status in orders["status"].unique():
        assert order_status_pt(status) != status
    for method in orders["payment_method"].unique():
        assert payment_method_pt(method) != method


@pytest.mark.parametrize(
    "when, expected",
    [
        (datetime(2026, 11, 3, 14, 0), "aberta até as 18h"),  # Tuesday afternoon
        (datetime(2026, 11, 3, 18, 0), "volta amanhã às 9h"),  # Tuesday, closing time
        (datetime(2026, 11, 2, 7, 30), "volta hoje às 9h"),  # Monday before opening
        (datetime(2026, 11, 7, 14, 0), "volta na segunda-feira às 9h"),  # Saturday after 13h
        (datetime(2026, 11, 8, 22, 0), "volta amanhã às 9h"),  # Sunday night
    ],
)
def test_store_status_knows_when_the_team_is_back(when, expected):
    assert expected in store_status(when)
