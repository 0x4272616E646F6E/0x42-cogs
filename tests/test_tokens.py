"""The estimator must never come in under a real tokenizer's count.

REFERENCE_COUNTS were produced once with tiktoken's cl100k_base over
representative Discord content. They are baked in so the suite needs no
tokenizer dependency of its own.
"""

from aiagent.utils.tokens import estimate_tokens

REFERENCE_COUNTS = {
    "hey does anyone know why my docker container keeps restarting every 30 seconds": 14,
    "lol same": 2,
    'User "brandon" said: @Red what is the discrete logarithm problem?': 17,
    "```python\ndef fib(n):\n    return n if n < 2 else fib(n-1)+fib(n-2)\n```": 27,
    "check https://github.com/ggml-org/llama.cpp/blob/master/examples/server/README.md": 20,
    "😂😂 that's wild <:pepe:12345> <:kek:67890> gg": 21,
    (
        "You are Red. You are in a Discord text channel. Respond to anything, "
        "including URLs, helpfully in a short message. Fulfill your persona and "
        "don't speak in third person."
    ): 38,
    "これはテストです。トークン数を数えます。": 16,
    '{"temperature": 0.8, "top_k": 40, "repetition_penalty": 1.1, "min_p": 0.05}': 34,
    "I think the issue is that the model keeps losing context between messages. " * 6: 85,
}


def test_never_under_estimates_a_real_tokenizer():
    for text, actual in REFERENCE_COUNTS.items():
        assert estimate_tokens(text) >= actual, f"under-counted: {text[:40]!r}"


def test_stays_within_a_useful_margin():
    """Conservative is fine; wildly conservative would waste the context window."""
    for text, actual in REFERENCE_COUNTS.items():
        assert estimate_tokens(text) <= actual * 3, f"over-counted: {text[:40]!r}"


def test_empty_text_costs_nothing():
    assert estimate_tokens("") == 0


def test_wide_characters_cost_more_than_ascii():
    assert estimate_tokens("これは") > estimate_tokens("abc")


def test_estimate_grows_with_length():
    short = estimate_tokens("hello world")
    assert estimate_tokens("hello world" * 10) > short


def test_result_is_a_whole_number_of_tokens():
    assert isinstance(estimate_tokens("a"), int)
    assert estimate_tokens("a") >= 1
