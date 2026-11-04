"""Stand-ins for the LLM tests: a fake HTTP transport (no request leaves the test,
Ollama on localhost included) and canned provider answers."""

import json

import llm_providers as lp

OLLAMA = "http://localhost:11434"
OPENAI = "https://api.openai.com/v1"
ANTHROPIC = "https://api.anthropic.com/v1"
NVIDIA = "https://integrate.api.nvidia.com/v1"


class FakeHttp:
    """Answers requests from ``routes``: {(method, url prefix): (status, data), an
    exception, or a callable(method, url, headers, body, timeout)}; the longest
    prefix wins. Records every request (method, url, headers, body, timeout). With
    no route a request fails as a stopped server does."""

    def __init__(self, routes=None):
        self.routes = dict(routes or {})
        self.requests = []

    def __call__(self, method, url, headers, body, timeout):
        self.requests.append((method, url, dict(headers), body, timeout))
        for (m, prefix), answer in sorted(
            self.routes.items(), key=lambda kv: -len(kv[0][1])
        ):
            if m == method and url.startswith(prefix):
                if isinstance(answer, Exception):
                    raise answer
                if callable(answer):
                    return answer(method, url, headers, body, timeout)
                status, data = answer
                return lp.HttpResponse(status, data, json.dumps(data))
        raise lp.ProviderUnavailable("could not connect (no route)")

    def posts(self):
        return [r for r in self.requests if r[0] == "POST"]


def openai_models(*rows):
    return (200, {"object": "list", "data": [dict(id=i, created=c) for i, c in rows]})


def chat_answer(text, prompt_tokens=100, completion_tokens=50):
    return (
        200,
        {
            "choices": [{"message": {"role": "assistant", "content": text}}],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
            },
        },
    )


def ollama_routes(answer="", models=("local:7b",)):
    """A running Ollama with ``models`` that answers every chat with ``answer``
    (a str, or a callable(prompt) -> str)."""

    def chat(method, url, headers, body, timeout):
        prompt = body["messages"][-1]["content"]
        text = answer(prompt) if callable(answer) else answer
        return lp.HttpResponse(
            200,
            {"message": {"content": text}, "prompt_eval_count": 50, "eval_count": 20},
        )

    return {
        ("GET", OLLAMA + "/api/version"): (200, {"version": "test"}),
        ("GET", OLLAMA + "/api/tags"): (200, {"models": [{"name": m} for m in models]}),
        ("POST", OLLAMA + "/api/chat"): chat,
    }
