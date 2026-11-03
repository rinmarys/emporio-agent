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
from langchain_groq import ChatGroq
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


def build_model(model: str, max_retries: int = 2):
    """One Groq chat model (D2). Swapping models is a .env change."""
    if not config.GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY is missing in .env")
    return ChatGroq(
        model=model,
        api_key=config.GROQ_API_KEY,
        temperature=TEMPERATURE,
        timeout=60,
        max_retries=max_retries,
        reasoning_format="hidden",  # the model's reasoning must never reach the customer
    )


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
    chain = list(dict.fromkeys([config.GROQ_MODEL, *config.GROQ_FALLBACK_MODELS]))  # no model twice
    # Free tier quotas are per model (8K tokens/min, ~200K tokens/day each). One retry rides out the
    # per-minute 429 (Groq asks for seconds); a daily 429 asks for minutes, so the client backs off
    # ~0.5s and we move to the next model. The last model retries more: nothing left to fall back to.
    models = [build_model(m, max_retries=1) for m in chain[:-1]] + [build_model(chain[-1])]
    middleware = [prompt_with_clock]
    if len(models) > 1:
        middleware.append(ModelFallbackMiddleware(*models[1:]))
    return create_agent(models[0], tools=TOOLS, middleware=middleware, checkpointer=MemorySaver())


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
                        if model := getattr(msg, "response_metadata", {}).get("model_name"):
                            logger.info("Thread %s answered by %s", thread_id, model)  # shows fallbacks
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
