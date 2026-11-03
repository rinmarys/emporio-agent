"""Tools the agent calls. They return structured data, never ready-made answers."""

import json
import unicodedata
from datetime import date

import pandas as pd
from langchain_core.tools import tool

from app.data_store import get_products, load_tables
from app.rules import (
    SELLABLE,
    discounted,
    needs_human,
    order_status_pt,
    payment_method_pt,
    payment_options,
)

MAX_RESULTS = 10


def normalize(text: str) -> str:
    """Lowercase and strip accents: 'Violão' -> 'violao'."""
    decomposed = unicodedata.normalize("NFKD", str(text))
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


def clean(value):
    """NaN from the CSVs becomes None so the model never sees 'nan'."""
    return None if pd.isna(value) else value


def product_view(row) -> dict:
    """Public product fields only. stock_quantity is never returned (D8-4b)."""
    view = {
        "name": row["name"],
        "category": row["category"],
        "description": row["description"],
        "specs": json.loads(row["specs"]) if isinstance(row["specs"], str) else None,
        "price_brl": row["price_brl"],
        "availability": row["availability"],
    }
    if row["promotions"]:
        # Manual 6.2: original price, percent and final price always shown together.
        view["original_price"] = row["price_brl"]
        view["promotions"] = [
            {
                "promo_name": p["description"],
                "discount_percent": p["discount_percent"],
                "final_price": discounted(row["price_brl"], p["discount_percent"]),
            }
            for p in row["promotions"]
        ]
    return view


@tool
def search_products(
    query: str | None = None,
    category: str | None = None,
    max_price: float | None = None,
    only_available: bool = True,
) -> dict:
    """Search the store catalog. Use for any question about products, prices, availability or options.

    Args:
        query: words to find in product name, description or category (e.g. "takamine gd20", "violao nylon").
        category: exact category name, one of: Guitarras, Baixos, Baterias e Percussão, Teclados e Pianos,
            Violões, Instrumentos de Sopro (Madeiras), Instrumentos de Sopro (Metais), Cordas Orquestrais, Ukuleles.
        max_price: highest price in BRL.
        only_available: keep only products that can be bought now. If none match, unavailable ones are
            returned with their availability label so you can explain and suggest alternatives.
    """
    products = get_products()
    haystack = (products["name"] + " " + products["description"] + " " + products["category"]).map(normalize)
    mask = pd.Series(True, index=products.index)
    for word in normalize(query or "").split():
        mask &= haystack.str.contains(word, regex=False)
    if category:
        names = load_tables()["categories"]["name"]
        if not names.map(normalize).str.contains(normalize(category), regex=False).any():
            # e.g. "Violão" vs "Violões": let the model retry instead of saying "we don't have it"
            return {"products": [], "message": "categoria não encontrada", "categories": names.tolist()}
        mask &= products["category"].map(normalize).str.contains(normalize(category), regex=False)
    if max_price is not None:
        mask &= products["price_brl"] <= max_price
    matches = products[mask]
    if matches.empty and query and category:
        # The model sometimes guesses the category of a named product wrong ("Takamine GD20" -> Guitarras).
        result = search_products.func(query=query, max_price=max_price, only_available=only_available)
        result["note"] = f"nenhum produto em '{category}'; resultados de outras categorias"
        return result

    if only_available and matches["availability"].isin(SELLABLE).any():
        matches = matches[matches["availability"].isin(SELLABLE)]
    if matches.empty:
        return {"products": [], "message": "nenhum produto encontrado"}
    matches = matches.sort_values("price_brl")
    return {
        "products": [product_view(row) for _, row in matches.head(MAX_RESULTS).iterrows()],
        "total_found": len(matches),
    }


@tool
def get_active_promotions() -> dict:
    """List every promotion active right now, with original price, discount percent and final price."""
    promos = [
        {
            "product": row["name"],
            "availability": row["availability"],
            "original_price": row["price_brl"],
            "promo_name": p["description"],
            "discount_percent": p["discount_percent"],
            "final_price": discounted(row["price_brl"], p["discount_percent"]),
        }
        for _, row in get_products().iterrows()
        for p in row["promotions"]
    ]
    if not promos:
        return {"promotions": [], "message": "nenhuma promoção ativa no momento"}
    return {"promotions": promos}


@tool
def get_payment_options(price_brl: float, is_promotional: bool) -> dict:
    """Payment options for a price: PIX discount, debit, boleto and allowed credit card installments.

    Args:
        price_brl: the price the customer will pay (use final_price when the product is on promotion).
        is_promotional: true if that price already has a promotion (then PIX gets no extra discount).
    """
    if not price_brl > 0:
        return {"message": "preço inválido; informe um valor maior que zero"}
    return payment_options(round(price_brl, 2), is_promotional)


@tool
def get_order_status(order_id: int) -> dict:
    """Look up an order by its number: status, items, total, payment, tracking and delivery estimate.

    Args:
        order_id: the order number given by the customer.
    """
    tables = load_tables()
    orders = tables["orders"]
    found = orders[orders["order_id"] == order_id]
    if found.empty:
        return {"found": False, "message": f"pedido {order_id} não encontrado"}
    order = found.iloc[0]

    items = tables["order_items"].query("order_id == @order_id").merge(
        tables["products"][["product_id", "name"]], on="product_id", how="left"
    )
    estimated = clean(order["estimated_delivery"])
    # Customer name, phone, email and city are never returned (D9).
    return {
        "found": True,
        "order_id": int(order["order_id"]),
        "status": order_status_pt(order["status"]),
        "order_date": order["order_date"],
        "payment_method": payment_method_pt(order["payment_method"]),
        "items": [{"name": i["name"], "quantity": int(i["quantity"])} for _, i in items.iterrows()],
        "total_brl": order["total_brl"],
        "tracking_code": clean(order["tracking_code"]),
        "estimated_delivery": estimated,
        "notes": clean(order["notes"]),
        "needs_human": needs_human(order["status"], estimated, date.today().isoformat()),
    }
