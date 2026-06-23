"""OpenAI Responses API implementation of the provider-neutral LLM client."""

from __future__ import annotations

from pydantic import BaseModel, ValidationError

from bayesify.llm.base import LLMError, LLMResponse, LLMTransientError, brace_json, usage_tokens


class OpenAIClient:
    """LLM client backed by OpenAI's Responses API."""

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key
        self._sdk_client = None

    def _client(self):
        if self._sdk_client is None:
            from openai import OpenAI

            self._sdk_client = OpenAI(api_key=self._api_key)
        return self._sdk_client

    def complete[T: BaseModel](
        self,
        *,
        model: str,
        system: str,
        user: str,
        schema: type[T],
        max_tokens: int = 1024,
    ) -> LLMResponse[T]:
        try:
            import openai
        except ImportError as exc:  # pragma: no cover - dependency is declared
            raise LLMError("the 'openai' SDK is not installed") from exc

        try:
            response = self._complete(model, system, user, schema, max_tokens=max_tokens)
        except openai.APIError as exc:
            status = getattr(exc, "status_code", None)
            if status is None or status >= 500 or status == 429:
                raise LLMTransientError(str(exc)) from exc
            raise LLMError(str(exc)) from exc

        parsed = _parsed_output(response, schema)
        if parsed is None:
            raise LLMTransientError("OpenAI returned no parseable structured output")
        input_tokens, output_tokens = usage_tokens(getattr(response, "usage", None))
        return LLMResponse(
            parsed=parsed, model=model, input_tokens=input_tokens, output_tokens=output_tokens
        )

    def _complete[T: BaseModel](
        self,
        model: str,
        system: str,
        user: str,
        schema: type[T],
        *,
        max_tokens: int,
    ):
        responses = self._client().responses
        input_messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        if hasattr(responses, "parse"):
            return responses.parse(
                model=model,
                input=input_messages,
                text_format=schema,
                max_output_tokens=max_tokens,
                store=False,
            )
        return responses.create(
            model=model,
            input=input_messages,
            max_output_tokens=max_tokens,
            store=False,
            text={
                "format": {
                    "type": "json_schema",
                    "name": _schema_name(schema),
                    "schema": schema.model_json_schema(),
                }
            },
        )


def _schema_name(schema: type[BaseModel]) -> str:
    return "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in schema.__name__)[:64]


def _parsed_output[T: BaseModel](response: object, schema: type[T]) -> T | None:
    parsed = getattr(response, "output_parsed", None)
    if isinstance(parsed, schema):
        return parsed
    if isinstance(parsed, dict):
        try:
            return schema.model_validate(parsed)
        except ValidationError as exc:
            raise LLMTransientError(f"OpenAI output failed schema validation: {exc}") from exc

    text = getattr(response, "output_text", None)
    if isinstance(text, str) and text.strip():
        try:
            return schema.model_validate_json(text)
        except ValidationError:
            data = brace_json(text)
            if data is not None:
                try:
                    return schema.model_validate(data)
                except ValidationError as exc:
                    raise LLMTransientError(
                        f"OpenAI output failed schema validation: {exc}"
                    ) from exc
        except ValueError:
            pass

    output = getattr(response, "output", None)
    if isinstance(output, list):
        chunks: list[str] = []
        for item in output:
            content = getattr(item, "content", None)
            if isinstance(content, list):
                for block in content:
                    block_parsed = getattr(block, "parsed", None)
                    if isinstance(block_parsed, schema):
                        return block_parsed
                    if isinstance(block_parsed, dict):
                        return schema.model_validate(block_parsed)
                    block_text = getattr(block, "text", None)
                    if isinstance(block_text, str):
                        chunks.append(block_text)
        data = brace_json("\n".join(chunks))
        if data is not None:
            try:
                return schema.model_validate(data)
            except ValidationError as exc:
                raise LLMTransientError(f"OpenAI output failed schema validation: {exc}") from exc
    return None

