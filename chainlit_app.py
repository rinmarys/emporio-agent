"""Browser chat (D5). Run: chainlit run chainlit_app.py

Interface only: every business rule lives in app/. One conversation per browser tab (D6).
Each reply ends with a collapsible "Como cheguei nisso" panel listing what the agent consulted.
"""

import chainlit as cl

from app import data_store
from app.agent import ERROR_MESSAGE, LOOP_MESSAGE, stream

STEP_LABELS = {
    "search_products": "Consultou o catálogo",
    "get_active_promotions": "Consultou as promoções ativas",
    "get_payment_options": "Calculou as formas de pagamento",
    "get_order_status": "Consultou o pedido",
    "get_store_policy": "Consultou o manual de políticas",
}
SOURCES = {
    "search_products": ["products.csv · produtos", "categories.csv · categorias", "promotions.csv · promoções"],
    "get_active_promotions": ["promotions.csv · promoções", "products.csv · produtos"],
    "get_payment_options": ["manual §3 · pagamento", "manual §6.2 · promoções"],
    "get_order_status": ["orders.csv · pedidos", "order_items.csv · itens do pedido"],
    "get_store_policy": ["knowledge/policies.md · manual da loja"],
}
ARG_LABELS = {
    "query": "busca",
    "category": "categoria",
    "max_price": "preço até",
    "only_available": "só disponíveis",
    "price_brl": "valor",
    "is_promotional": "preço promocional",
    "order_id": "pedido",
    "topic": "tópico",
}


def brl(value: float) -> str:
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def describe_arg(key: str, value) -> str:
    if isinstance(value, bool):
        value = "sim" if value else "não"
    elif key in ("max_price", "price_brl") and isinstance(value, (int, float)):
        value = brl(value)
    return f"{ARG_LABELS.get(key, key)}: {value}"


def panel_props(calls: list[dict]) -> dict:
    """What the "Como cheguei nisso" panel shows, from the tool calls of one answer."""
    loaded = data_store.loaded_at.strftime("%d/%m/%Y %H:%M") if data_store.loaded_at else "—"
    return {
        "steps": [
            {
                "label": STEP_LABELS.get(c["name"], c["name"]),
                "filters": [describe_arg(k, v) for k, v in c["args"].items() if v not in (None, "")],
            }
            for c in calls
        ],
        "sources": list(dict.fromkeys(s for c in calls for s in SOURCES.get(c["name"], []))),
        "dataFrom": f"{loaded} · arquivos da loja carregados ao iniciar o atendimento",
        "access": "Somente leitura. Nenhum pedido, preço ou cadastro foi alterado.",
    }


@cl.set_starters
async def starters():
    return [
        cl.Starter(label="Violões até R$1.000", message="Quais violões vocês têm até R$1.000?"),
        cl.Starter(label="Quanto custa o Takamine GD20?", message="Quanto custa o Takamine GD20?"),
        cl.Starter(label="Quais promoções estão ativas?", message="Quais promoções estão ativas?"),
        cl.Starter(label="Qual o status do meu pedido?", message="Qual o status do meu pedido?"),
        cl.Starter(label="Como funciona a troca?", message="Como funciona a troca?"),
        cl.Starter(label="Horário e endereço da loja", message="Qual o horário e o endereço da loja?"),
    ]


@cl.on_message
async def on_message(message: cl.Message) -> None:
    reply = cl.Message(content="")
    calls = []
    async for kind, value in stream(message.content, thread_id=cl.context.session.id):
        if kind == "tool":
            calls.append(value)
        else:
            await reply.stream_token(value)
    if reply.content not in (ERROR_MESSAGE, LOOP_MESSAGE):  # no "how I got here" under an apology
        reply.elements = [cl.CustomElement(name="HowIGotHere", props=panel_props(calls), display="inline")]
    await reply.send()
