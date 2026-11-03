"""Store policy manual, queryable by fixed topic (D3)."""

import re
from functools import cache
from pathlib import Path

from langchain_core.tools import tool

from app.tools import normalize

POLICIES_FILE = Path(__file__).resolve().parent.parent / "knowledge" / "policies.md"


@cache
def load_policies() -> dict[str, str]:
    """Split policies.md on its '## <topic>' headings, once."""
    parts = re.split(r"^## (\w+)\s*$", POLICIES_FILE.read_text(encoding="utf-8"), flags=re.MULTILINE)
    # parts = [header comment, topic1, text1, topic2, text2, ...]
    return {topic: text.strip() for topic, text in zip(parts[1::2], parts[2::2])}


@tool
def get_store_policy(topic: str) -> dict:
    """Read one section of the store policy manual. Use it for any question about store rules or store info,
    never answer these from memory.

    Args:
        topic: one of
            sobre_a_loja: "o que vocês vendem?", "vendem cordas/pedais/amplificadores?", "desde quando existem?"
            contato: "qual o endereço?", "qual o telefone/WhatsApp?", "qual o e-mail?"
            horarios: "que horas abre?", "abre sábado?", "funciona no feriado?"
            pagamento: "aceita PIX?", "parcela em quantas vezes?", "posso pagar com boleto?"
            trocas_devolucoes: "me arrependi, posso devolver?", "veio com defeito", "quero trocar de cor"
            frete_entregas: "quanto custa o frete?", "entregam em outra cidade?", "qual o prazo de entrega?"
            promocoes: "quando tem Black Friday?", "desconto do PIX vale na promoção?"
            garantia: "qual a garantia?", "a garantia cobre queda?"
            privacidade: "o que fazem com meus dados?", "quero apagar meus dados"
    """
    policies = load_policies()
    key = normalize(topic).strip().replace(" ", "_")
    if key not in policies:
        return {"message": f"tópico inválido: {topic!r}", "valid_topics": list(policies)}
    return {"topic": key, "content": policies[key]}
