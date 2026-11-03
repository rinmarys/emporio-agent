from langgraph.errors import GraphRecursionError

from app import agent


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
