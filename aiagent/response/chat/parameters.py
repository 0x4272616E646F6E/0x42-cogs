"""Routing of user-supplied generation parameters to the OpenAI SDK.

The SDK accepts only the arguments it declares; anything else raises TypeError.
Backend-specific samplers (top_k, repetition_penalty, min_p, ...) therefore have
to travel in `extra_body`, which the SDK serialises as top-level JSON fields —
exactly where llama.cpp, vLLM and friends look for them.
"""

import inspect
from dataclasses import dataclass
from typing import Any, Dict, Optional

from openai.resources.chat.completions import AsyncCompletions

# Argument names the *installed* SDK declares for chat completions. Introspected
# rather than hardcoded, so a newer SDK passes its new parameters natively
# instead of having them misrouted into extra_body.
SDK_PARAMETERS = frozenset(inspect.signature(AsyncCompletions.create).parameters) - {"self"}


@dataclass(frozen=True)
class SamplingParameter:
    """A sampling knob exposed as its own command, with an accepted range."""

    key: str
    label: str
    minimum: float
    maximum: Optional[float] = None
    minimum_inclusive: bool = True
    integer: bool = False

    def describe_range(self) -> str:
        if self.maximum is None:
            return f"{self.minimum:g} or greater"
        if self.minimum_inclusive:
            return f"between {self.minimum:g} and {self.maximum:g}"
        return f"greater than {self.minimum:g} and at most {self.maximum:g}"

    def validate(self, value: float) -> Optional[str]:
        """Return an error message for an unacceptable value, else None."""
        if self.integer and float(value) != int(value):
            return f"`{self.key}` must be a whole number."
        if self.minimum_inclusive and value < self.minimum:
            return f"`{self.key}` must be {self.describe_range()}."
        if not self.minimum_inclusive and value <= self.minimum:
            return f"`{self.key}` must be {self.describe_range()}."
        if self.maximum is not None and value > self.maximum:
            return f"`{self.key}` must be {self.describe_range()}."
        return None


SAMPLING_PARAMETERS: Dict[str, SamplingParameter] = {
    "temperature": SamplingParameter(
        key="temperature", label="Temperature", minimum=0.0, maximum=2.0
    ),
    "top_k": SamplingParameter(
        key="top_k", label="Top K", minimum=0, maximum=None, integer=True
    ),
    "repetition_penalty": SamplingParameter(
        key="repetition_penalty",
        label="Repetition penalty",
        minimum=0.0,
        maximum=2.0,
        minimum_inclusive=False,
    ),
}


def split_parameters(params: Dict[str, Any]) -> Dict[str, Any]:
    """Split stored parameters into SDK kwargs, routing the rest via extra_body.

    Keys the SDK declares are returned as top-level kwargs. Everything else is
    collected into `extra_body`. An `extra_body` dict supplied by the user is
    merged last, so an explicit entry wins over the same key set at top level.
    """
    kwargs: Dict[str, Any] = {}
    extra_body: Dict[str, Any] = {}

    for name, value in params.items():
        if name == "extra_body":
            continue
        if name in SDK_PARAMETERS:
            kwargs[name] = value
        else:
            extra_body[name] = value

    explicit = params.get("extra_body")
    if isinstance(explicit, dict):
        extra_body.update(explicit)

    if extra_body:
        kwargs["extra_body"] = extra_body

    return kwargs
