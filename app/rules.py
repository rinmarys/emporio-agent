"""Business rules: pure functions, no data access."""

LOW_STOCK_LIMIT = 3  # D8-4b: documented assumption, 1..3 units = "últimas unidades"

# Contacts per D8-1 (general phone/WhatsApp + customer service WhatsApp).
# shortcut: contacts duplicated from the policy manual, read them from get_store_policy once T03 exists.
UNKNOWN_AVAILABILITY = (
    "não consegui confirmar a disponibilidade deste produto agora; "
    "fale com a nossa equipe pelo WhatsApp (67) 3321-4500 ou pelo telefone (67) 3341-4444"
)

ORDER_STATUS_PT = {
    "pending": "pendente",
    "confirmed": "confirmado",
    "shipped": "enviado",
    "delivered": "entregue",
    "cancelled": "cancelado",
}

PAYMENT_METHOD_PT = {
    "pix": "PIX",
    "debit": "cartão de débito",
    "boleto": "boleto bancário",
    "credit_3x": "cartão de crédito em 3x",
    "credit_6x": "cartão de crédito em 6x",
    "credit_12x": "cartão de crédito em 12x",
}


def availability(status: str, stock: int) -> str:
    """Customer-facing availability label. Status wins over stock (D8-5, D8-6)."""
    if status == "discontinued":
        return "fora de linha"
    if status == "coming_soon":
        return "em breve"
    if status != "active":
        return UNKNOWN_AVAILABILITY  # never guess availability (manual 7.1)
    if not stock >= 0:  # empty CSV cell (NaN) or negative stock: data we can't trust
        return UNKNOWN_AVAILABILITY
    if stock == 0:
        return "indisponível no momento"
    if stock <= LOW_STOCK_LIMIT:
        return "últimas unidades"
    return "disponível"


PIX_DISCOUNT_PERCENT = 5
COMBINED_PAYMENT_MIN_BRL = 2000
SELLABLE = {"disponível", "últimas unidades"}


def discounted(price: float, percent: float) -> float:
    return round(price * (1 - percent / 100), 2)


def min_installment(n: int) -> int:
    """Manual 3.1 bands (D8-3: up to 3x assumes R$50 minimum)."""
    return 50 if n <= 3 else 80 if n <= 6 else 100


def payment_options(price: float, is_promotional: bool) -> dict:
    """PIX, debit, boleto and credit installments for one price (manual 3 and 6.2)."""
    installments = [
        {"installments": n, "installment_value": round(price / n, 2)}
        for n in range(1, 13)
        if price / n >= min_installment(n)
    ]
    return {
        "price_brl": price,
        # PIX discount is not cumulative with promotions (manual 6.2)
        "pix": {
            "price_brl": price if is_promotional else discounted(price, PIX_DISCOUNT_PERCENT),
            "discount_percent": 0 if is_promotional else PIX_DISCOUNT_PERCENT,
        },
        "debit": {"price_brl": price},
        "boleto": {"price_brl": price, "note": "compensação em até 3 dias úteis"},
        "credit_card": {
            "max_installments": installments[-1]["installments"] if installments else 0,
            "options": installments,
            "interest": "sem juros",
        },
        "combined_payment_allowed": price > COMBINED_PAYMENT_MIN_BRL,
    }


def needs_human(status: str, estimated_delivery, today) -> bool:
    """Late order still open (D8-8): agent must not invent a reason, team takes over."""
    if status in ("delivered", "cancelled") or not estimated_delivery:
        return False
    return estimated_delivery < today


def order_status_pt(status: str) -> str:
    return ORDER_STATUS_PT.get(status, status)


def payment_method_pt(method: str) -> str:
    return PAYMENT_METHOD_PT.get(method, method)
