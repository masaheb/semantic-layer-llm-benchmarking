"""Preflight validation for benchmark configurations."""

from typing import get_args

from pydantic_ai.models import KnownModelName

from llm_bench.config.base import BaseConfig


KNOWN_MODELS: set[str] = set(get_args(KnownModelName.__value__))

OPENAI_REASONING_EFFORTS = {"none", "minimal", "low", "medium", "high", "xhigh", "max"}
ANTHROPIC_REASONING_EFFORTS = {"low", "medium", "high", "max"}


def validate_configs(configs: list[BaseConfig]) -> None:
    """Validate all configs before running benchmarks.

    Checks:
    - model_name uses "provider:model" format
    - model_name is in PydanticAI's KnownModelName registry
    - reasoning_effort is valid for the provider

    Raises ValueError with all errors collected.
    """
    errors: list[str] = []

    for i, config in enumerate(configs):
        prefix = f"Config {i + 1}" if len(configs) > 1 else "Config"
        name = config.model_name

        if ":" not in name:
            errors.append(f'{prefix}: model_name "{name}" must use "provider:model" format (e.g. "openai:gpt-5")')
            continue

        provider = name.split(":")[0]

        # Bedrock model ids (e.g. "bedrock:us.anthropic.claude-...-v1:0") are not in
        # PydanticAI's static KnownModelName registry; they are validated at call time
        # by Bedrock itself. Skip the registry check for them.
        if provider != "bedrock" and name not in KNOWN_MODELS:
            errors.append(f'{prefix}: model_name "{name}" is not in the PydanticAI known model registry')

        effort = config.reasoning_effort
        if effort is not None:
            if provider == "openai" and effort not in OPENAI_REASONING_EFFORTS:
                errors.append(
                    f'{prefix}: reasoning_effort "{effort}" invalid for OpenAI. '
                    f"Must be one of: {sorted(OPENAI_REASONING_EFFORTS)}"
                )
            elif provider == "anthropic" and effort not in ANTHROPIC_REASONING_EFFORTS:
                errors.append(
                    f'{prefix}: reasoning_effort "{effort}" invalid for Anthropic. '
                    f"Must be one of: {sorted(ANTHROPIC_REASONING_EFFORTS)}"
                )

    if errors:
        raise ValueError("Configuration validation failed:\n" + "\n".join(f"  - {e}" for e in errors))
