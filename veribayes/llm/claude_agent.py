"""Claude Agent SDK implementation of the provider-neutral LLM client."""

from __future__ import annotations

import json
import os

from pydantic import BaseModel, ValidationError

from veribayes.llm.base import (
    LLMError,
    LLMResponse,
    LLMTransientError,
    brace_json,
    run_sync,
    usage_tokens,
)


class AgentSDKClient:
    """LLM client backed by the Claude Agent SDK and local Claude Code session."""

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
            import claude_agent_sdk as sdk
        except ImportError as exc:  # pragma: no cover - dependency is declared
            raise LLMError("the 'claude-agent-sdk' package is not installed") from exc

        use_output_format = os.environ.get("VERIBAYES_AGENT_OUTPUT_FORMAT", "").strip().lower() in (
            "1",
            "true",
            "yes",
        )
        opts_kwargs: dict = dict(
            system_prompt=system,
            model=model,
            allowed_tools=[],
            max_turns=4,
            permission_mode="bypassPermissions",
        )
        prompt = user
        if use_output_format:
            opts_kwargs["output_format"] = {
                "type": "json_schema",
                "schema": schema.model_json_schema(),
            }
        else:
            prompt = (
                f"{user}\n\nRespond with ONLY a JSON object matching this JSON Schema - no prose, "
                f"no markdown fences:\n{json.dumps(schema.model_json_schema())}"
            )
        options = sdk.ClaudeAgentOptions(**opts_kwargs)

        async def _collect():
            chunks: list[str] = []
            result: dict = {"structured": None, "in": 0, "out": 0, "error": None}
            async for msg in sdk.query(prompt=prompt, options=options):
                if hasattr(msg, "structured_output") or hasattr(msg, "total_cost_usd"):
                    so = getattr(msg, "structured_output", None)
                    if isinstance(so, dict):
                        result["structured"] = so
                    result["in"], result["out"] = usage_tokens(getattr(msg, "usage", None))
                    if getattr(msg, "is_error", False):
                        result["error"] = getattr(msg, "result", None) or "agent SDK error"
                elif hasattr(msg, "content"):
                    for block in msg.content:
                        text = getattr(block, "text", None)
                        if isinstance(text, str):
                            chunks.append(text)
            return "".join(chunks).strip(), result

        try:
            text, result = run_sync(_collect)
        except Exception as exc:
            raise LLMTransientError(str(exc)) from exc

        if result["error"]:
            raise LLMError(f"agent SDK error: {result['error']}")
        data = result["structured"] if result["structured"] is not None else brace_json(text)
        if data is None:
            raise LLMTransientError(f"agent SDK returned no parseable JSON (got: {text[:200]!r})")
        try:
            parsed = schema.model_validate(data)
        except ValidationError as exc:
            raise LLMTransientError(f"agent SDK output failed schema validation: {exc}") from exc
        return LLMResponse(
            parsed=parsed, model=model, input_tokens=result["in"], output_tokens=result["out"]
        )
