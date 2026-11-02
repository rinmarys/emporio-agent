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


def order_status_pt(status: str) -> str:
    return ORDER_STATUS_PT.get(status, status)


def payment_method_pt(method: str) -> str:
    return PAYMENT_METHOD_PT.get(method, method)
