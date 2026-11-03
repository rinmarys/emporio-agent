"""Data repository: loads the CSVs once and joins them. No business decisions here."""

import logging
from datetime import datetime
from functools import cache
from pathlib import Path

import pandas as pd

from app.rules import UNKNOWN_AVAILABILITY, availability

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
TABLES = ("products", "categories", "promotions", "orders", "order_items", "customers")


loaded_at: datetime | None = None  # when the CSVs were read; shown to the customer as "data from"


@cache
def load_tables() -> dict[str, pd.DataFrame]:
    """Read every CSV once; later calls reuse the same DataFrames."""
    global loaded_at
    loaded_at = datetime.now()
    return {name: pd.read_csv(DATA_DIR / f"{name}.csv") for name in TABLES}


def build_products(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Products + category name + list of active promotions + availability label."""
    categories = tables["categories"][["category_id", "name"]].rename(columns={"name": "category"})
    # Promotions are not cumulative (manual 6.2): keep every active one so the customer can choose.
    # No date in the CSV, so highest promotion_id = most recent (documented assumption), listed first.
    active = tables["promotions"].query("is_active == 1").sort_values("promotion_id", ascending=False)
    promotions_by_product: dict[int, list[dict]] = {}
    for promo in active.to_dict("records"):
        promotions_by_product.setdefault(promo["product_id"], []).append(
            {k: promo[k] for k in ("promotion_id", "description", "discount_percent")}
        )
    products = tables["products"].merge(categories, on="category_id", how="left")
    products["promotions"] = [promotions_by_product.get(pid, []) for pid in products["product_id"]]
    # One text cell turns the whole column into text; bad cells become NaN -> "talk to the team".
    products["stock_quantity"] = pd.to_numeric(products["stock_quantity"], errors="coerce")

    products["availability"] = [
        availability(status, stock)
        for status, stock in zip(products["status"], products["stock_quantity"])
    ]
    unknown = products[products["availability"] == UNKNOWN_AVAILABILITY]
    for _, row in unknown.iterrows():
        logger.warning(
            "Untrusted data for product %s (%s): status=%r stock=%r",
            row["product_id"], row["name"], row["status"], row["stock_quantity"],
        )
    return products


@cache
def get_products() -> pd.DataFrame:
    """Enriched products table, built once from the CSVs."""
    return build_products(load_tables())
