"""The agent: model + tools + prompt + per-conversation memory (D1, D2, D6).

Interfaces only call ask(message, thread_id), or stream(...) for chat UIs that show steps.
"""

import logging
from datetime import datetime
from functools import cache
from zoneinfo import ZoneInfo

from langchain.agents import create_agent
from langchain.agents.middleware import ModelFallbackMiddleware, ModelRequest, dynamic_prompt
from langchain_core.messages import AIMessageChunk
from langgraph.checkpoint.memory import MemorySaver
from langgraph.errors import GraphRecursionError

from app import config
from app.data_store import get_products
from app.policies import get_store_policy
from app.prompt import SYSTEM_PROMPT
from app.rules import store_status
from app.tools import get_active_promotions, get_order_status, get_payment_options, search_products

logger = logging.getLogger(__name__)

TOOLS = [search_products, get_active_promotions, get_payment_options, get_order_status, get_store_policy]
RECURSION_LIMIT = 12  # model/tool steps per question, so a confused model cannot loop forever
TEMPERATURE = 0.2
STORE_TZ = ZoneInfo("America/Campo_Grande")

ERROR_MESSAGE = (
    "Opa, tive um problema técnico para responder agora 😕 Pode tentar de novo em instantes? "
    "Se preferir, fale com a nossa equipe pelo WhatsApp (67) 3321-4500 ou pelo telefone (67) 3341-4444."
)
LOOP_MESSAGE = (
    "Não consegui chegar a uma resposta para essa pergunta. Pode reformular de outro jeito? "
    "Se preferir, a nossa equipe atende pelo WhatsApp (67) 3321-4500."
)


def build_model(provider: str = config.LLM_PROVIDER, max_retries: int = 2):
    """Chat model for the configured provider; switching is one .env variable (D2)."""
    common = {"temperature": TEMPERATURE, "timeout": 60, "max_retries": max_retries}
    if provider == "gemini":
        if not config.GOOGLE_API_KEY:
            raise RuntimeError("GOOGLE_API_KEY is missing in .env")
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(model=config.GEMINI_MODEL, api_key=config.GOOGLE_API_KEY, **common)
    if provider == "groq":
        if not config.GROQ_API_KEY:
            raise RuntimeError("GROQ_API_KEY is missing in .env")
        from langchain_groq import ChatGroq

        return ChatGroq(model=config.GROQ_MODEL, api_key=config.GROQ_API_KEY, **common)
    raise RuntimeError(f"LLM_PROVIDER must be 'gemini' or 'groq', got {provider!r}")


def store_now() -> datetime:
    return datetime.now(STORE_TZ)


@dynamic_prompt
def prompt_with_clock(request: ModelRequest) -> str:
    """System prompt + current Campo Grande time and open/closed status, rebuilt on every model call."""
    return (
        f"{SYSTEM_PROMPT}\n## Agora\n{store_status(store_now())}\n"
        "Se a loja estiver fechada e você indicar a equipe, diga primeiro que a loja está fechada agora "
        "e quando a equipe volta, usando exatamente o dia e a hora acima.\n"
    )


@cache
def get_agent():
    """Built once per process. MemorySaver keeps each thread_id's history in RAM (D6)."""
    get_products()  # load the CSVs at startup, not on the first customer question
    other = "gemini" if config.LLM_PROVIDER == "groq" else "groq"
    other_key = config.GOOGLE_API_KEY if other == "gemini" else config.GROQ_API_KEY
    if not other_key:
        return create_agent(
            build_model(), tools=TOOLS, middleware=[prompt_with_clock], checkpointer=MemorySaver()
        )
    # Free tiers hit 429 often: fail fast on the main provider and switch to the other one,
    # instead of waiting up to ~40s for the main provider's retry.
    return create_agent(
        build_model(max_retries=0),
        tools=TOOLS,
        checkpointer=MemorySaver(),
        middleware=[prompt_with_clock, ModelFallbackMiddleware(build_model(other))],
    )


async def stream(message: str, thread_id: str):
    """Async version of ask for chat UIs. Yields ("tool", {"name", "args"}) when a tool is called and
    ("text", chunk) while the reply is generated. Never raises to the interface."""
    config_ = {"configurable": {"thread_id": thread_id}, "recursion_limit": RECURSION_LIMIT}
    try:
        async for mode, data in get_agent().astream(
            {"messages": [{"role": "user", "content": message}]}, config_, stream_mode=["updates", "messages"]
        ):
            if mode == "updates":
                for update in data.values():
                    for msg in (update or {}).get("messages", []):
                        for call in getattr(msg, "tool_calls", None) or []:
                            yield "tool", {"name": call["name"], "args": call["args"]}
            else:
                chunk, meta = data
                if meta.get("langgraph_node") == "model" and isinstance(chunk, AIMessageChunk) and chunk.text:
                    yield "text", chunk.text
    except GraphRecursionError:
        logger.warning("Recursion limit hit for thread %s", thread_id)
        yield "text", LOOP_MESSAGE
    except Exception:
        logger.exception("Agent stream failed for thread %s", thread_id)
        yield "text", ERROR_MESSAGE


def ask(message: str, thread_id: str) -> str:
    """Send one customer message and return the agent's reply. Never raises to the interface."""
    config_ = {"configurable": {"thread_id": thread_id}, "recursion_limit": RECURSION_LIMIT}
    try:
        result = get_agent().invoke({"messages": [{"role": "user", "content": message}]}, config_)
        return result["messages"][-1].text
    except GraphRecursionError:
        logger.warning("Recursion limit hit for thread %s", thread_id)
        return LOOP_MESSAGE
    except Exception:
        # Quota (429), network or provider errors: log the details, show a friendly message.
        logger.exception("Agent call failed for thread %s", thread_id)
        return ERROR_MESSAGE
