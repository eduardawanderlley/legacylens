from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Completion:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0


class LLM(Protocol):
    def complete(self, system: str, messages: list[dict[str, str]], max_tokens: int = 1500) -> Completion: ...


class AnthropicLLM:
    """Adaptador fino para a API da Anthropic. Troque por outro provedor implementando `LLM`."""

    def __init__(self, model: str, api_key: str | None = None) -> None:
        import anthropic  # import tardio: só quem usa LLM real precisa do SDK

        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def complete(self, system: str, messages: list[dict[str, str]], max_tokens: int = 1500) -> Completion:
        resp = self._client.messages.create(
            model=self._model, system=system, messages=messages, max_tokens=max_tokens, temperature=0
        )
        text = "".join(block.text for block in resp.content if block.type == "text")
        return Completion(text, resp.usage.input_tokens, resp.usage.output_tokens)
