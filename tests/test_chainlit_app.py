from chainlit_app import panel_props


def test_panel_lists_steps_filters_and_sources_in_pt_br():
    props = panel_props([
        {"name": "search_products", "args": {"category": "Violões", "max_price": 1000, "query": None}},
        {"name": "get_payment_options", "args": {"price_brl": 2199.0, "is_promotional": False}},
    ])
    assert props["steps"] == [
        {"label": "Consultou o catálogo", "filters": ["categoria: Violões", "preço até: R$ 1.000,00"]},
        {"label": "Calculou as formas de pagamento", "filters": ["valor: R$ 2.199,00", "preço promocional: não"]},
    ]
    assert "products.csv · produtos" in props["sources"]
    assert len(props["sources"]) == len(set(props["sources"]))  # no duplicates


def test_panel_without_tools_says_so():
    props = panel_props([])
    assert props["steps"] == [] and props["sources"] == []
    assert "Somente leitura" in props["access"]
