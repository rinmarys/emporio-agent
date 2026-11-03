import asyncio

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langgraph.errors import GraphRecursionError

from app import agent, config


class FakeModel(GenericFakeChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


class RateLimitedModel(FakeModel):
    async def _astream(self, *args, **kwargs):
        raise RuntimeError("429 Too Many Requests")
        yield  # makes this an async generator


def test_429_walks_the_fallback_chain_and_last_model_retries_most(monkeypatch):
    built = []

    def fake_build_model(model, max_retries=2):
        built.append((model, max_retries))
        if model == "last":
            return FakeModel(messages=iter([AIMessage(content="resposta do último modelo")]))
        return RateLimitedModel(messages=iter([]))

    monkeypatch.setattr(config, "GROQ_MODEL", "main")
    monkeypatch.setattr(config, "GROQ_FALLBACK_MODELS", ["middle", "main", "last"])  # duplicate is skipped
    monkeypatch.setattr(agent, "build_model", fake_build_model)
    agent.get_agent.cache_clear()
    try:
        async def collect():
            return "".join([v async for kind, v in agent.stream("oi", "fallback-test") if kind == "text"])

        assert asyncio.run(collect()) == "resposta do último modelo"
        assert built == [("main", 1), ("middle", 1), ("last", 2)]
    finally:
        agent.get_agent.cache_clear()  # don't leak the fake agent into other tests


class FailingAgent:
    def __init__(self, error):
        self.error = error

    def invoke(self, *_args, **_kwargs):
        raise self.error


def test_provider_error_becomes_friendly_message(monkeypatch):
    monkeypatch.setattr(agent, "get_agent", lambda: FailingAgent(RuntimeError("429 RESOURCE_EXHAUSTED")))
    assert agent.ask("oi", "t1") == agent.ERROR_MESSAGE


def test_loop_becomes_friendly_message(monkeypatch):
    monkeypatch.setattr(agent, "get_agent", lambda: FailingAgent(GraphRecursionError("limit")))
    assert agent.ask("oi", "t1") == agent.LOOP_MESSAGE
