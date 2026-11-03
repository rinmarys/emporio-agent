import pytest

from app.policies import get_store_policy, load_policies

TOPICS = [
    "sobre_a_loja", "contato", "horarios", "pagamento", "trocas_devolucoes",
    "frete_entregas", "promocoes", "garantia", "privacidade",
]


def policy(topic):
    return get_store_policy.invoke({"topic": topic})


def test_exactly_the_nine_fixed_topics():
    assert list(load_policies()) == TOPICS


@pytest.mark.parametrize(
    "topic, expected",
    [
        ("sobre_a_loja", "exclusivamente com instrumentos musicais"),
        ("contato", "Rua 14 de Maio, 3200"),
        ("horarios", "09:00 às 13:00"),
        ("pagamento", "Até 12x sem juros"),
        ("trocas_devolucoes", "7 (sete) dias corridos"),
        ("frete_entregas", "Frete grátis para pedidos acima de R$ 500,00"),
        ("promocoes", "não são cumulativas"),
        ("garantia", "90 (noventa) dias"),
        ("privacidade", "LGPD"),
    ],
)
def test_each_topic_returns_its_section(topic, expected):
    result = policy(topic)
    assert result["topic"] == topic
    assert expected in result["content"]


def test_topics_do_not_leak_into_each_other():
    assert "Frete grátis" not in policy("pagamento")["content"]
    assert "09:00" not in policy("garantia")["content"]


def test_d8_corrections():
    contact = policy("contato")["content"]
    assert "(67) 3341-4444" in contact and "(67) 3321-4500" in contact  # D8-1
    assert "contato@emporiodamusica.com.br" in contact  # D8-2
    assert "parcela mínima de R$ 50,00" in policy("pagamento")["content"]  # D8-3


def test_service_guidelines_are_not_a_topic():
    assert "Tom de voz" not in str(load_policies())  # section 7 goes to the system prompt


def test_topic_is_accent_and_case_insensitive():
    assert policy("Horários")["topic"] == "horarios"


def test_invalid_topic_returns_valid_topics():
    result = policy("cardapio")
    assert "inválido" in result["message"]
    assert result["valid_topics"] == TOPICS
