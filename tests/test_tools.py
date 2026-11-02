import json

from app.rules import needs_human
from app.tools import get_active_promotions, get_order_status, get_payment_options, search_products


def search(**kwargs):
    return search_products.invoke(kwargs)


def test_takamine_gd20_has_price_and_availability():
    result = search(query="Takamine GD20")
    [gd20] = result["products"]
    assert gd20["price_brl"] == 2199.0
    assert gd20["availability"] == "disponível"


def test_search_ignores_accents_and_case():
    assert search(query="VIOLAO")["products"]
    assert all(p["category"] == "Violões" for p in search(category="violoes")["products"])


def test_unknown_category_returns_real_names_instead_of_not_found():
    result = search(category="Violão")  # singular: not inside "Violões"
    assert result["message"] == "categoria não encontrada"
    assert "Violões" in result["categories"]


def test_search_limit_price_filter_and_empty_result():
    result = search(category="Violões", max_price=1000)
    assert 0 < len(result["products"]) <= 10
    assert all(p["price_brl"] <= 1000 for p in result["products"])
    assert search(query="cabo p10") == {"products": [], "message": "nenhum produto encontrado"}


def test_stock_quantity_is_never_returned():
    payload = json.dumps(search(max_price=100000, only_available=False), ensure_ascii=False)
    assert "stock" not in payload


def test_unavailable_product_is_still_found_with_its_label():
    [ibanez] = search(query="Ibanez Bass 2X")["products"]
    assert ibanez["availability"] == "fora de linha"


def test_promotional_price_shows_original_percent_and_final():
    [kalani] = search(query="KAL-700T")["products"]
    assert kalani["original_price"] == 359.0
    assert kalani["promotions"] == [
        {"promo_name": "Oferta Especial", "discount_percent": 10, "final_price": 323.1}
    ]
    assert len(get_active_promotions.invoke({})["promotions"]) == 4


def test_promotional_price_gets_no_pix_discount():
    assert get_payment_options.invoke({"price_brl": 323.1, "is_promotional": True})["pix"] == {
        "price_brl": 323.1,
        "discount_percent": 0,
    }
    assert get_payment_options.invoke({"price_brl": 2199.0, "is_promotional": False})["pix"] == {
        "price_brl": 2089.05,
        "discount_percent": 5,
    }


def test_installment_bands():
    # Giannini GNF-3 CEQ, R$1.049: 12x = R$87.42 (< R$100, refused), 10x = R$104.90 (accepted)
    card = get_payment_options.invoke({"price_brl": 1049.0, "is_promotional": False})["credit_card"]
    assert card["max_installments"] == 10
    assert {"installments": 10, "installment_value": 104.9} in card["options"]
    assert all(o["installments"] != 12 for o in card["options"])
    # 4x-6x band needs R$80: R$400 allows 5x (R$80) but not 6x (R$66.67)
    assert get_payment_options.invoke({"price_brl": 400.0, "is_promotional": False})["credit_card"][
        "max_installments"
    ] == 5


def test_combined_payment_only_above_2000():
    assert get_payment_options.invoke({"price_brl": 2199.0, "is_promotional": False})["combined_payment_allowed"]
    assert not get_payment_options.invoke({"price_brl": 2000.0, "is_promotional": False})["combined_payment_allowed"]


def test_invalid_price_is_rejected():
    assert "message" in get_payment_options.invoke({"price_brl": 0, "is_promotional": False})


def test_order_does_not_expose_customer_data():
    order = get_order_status.invoke({"order_id": 1})
    assert order["status"] == "entregue" and order["payment_method"] == "PIX"
    assert order["items"] and order["tracking_code"] == "BRAB1234567BR"
    payload = json.dumps(order, ensure_ascii=False)
    for secret in ("customer", "Campo Grande", "@", "(67)", "Silva"):
        assert secret not in payload


def test_cancelled_order_returns_reason():
    order = get_order_status.invoke({"order_id": 17})
    assert order["status"] == "cancelado" and "cancelado pelo cliente" in order["notes"]
    assert order["needs_human"] is False


def test_late_open_order_needs_human():
    order = get_order_status.invoke({"order_id": 8})  # shipped, estimated 2026-02-28
    assert order["needs_human"] is True
    assert needs_human("shipped", "2026-02-28", "2026-02-27") is False  # not late yet
    assert needs_human("delivered", "2026-02-28", "2026-12-01") is False


def test_unknown_order_has_clear_message():
    assert get_order_status.invoke({"order_id": 999}) == {
        "found": False,
        "message": "pedido 999 não encontrado",
    }
