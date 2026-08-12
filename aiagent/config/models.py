"""Context window sizes for commonly self-hosted models.

Local OpenAI-compatible servers (Ollama, llama.cpp, vLLM, LM Studio, ...) do not
report a context length through `/v1/models`, so the cog estimates one from the
model name. The estimate is only used to decide how much channel history to send;
`[p]aiagent history customtokenlimit` sets an explicit override per server when it
is wrong.
"""

from aiagent.config.defaults import DEFAULT_TOKENS_LIMIT

# Matched against the model name, longest match wins.
# Values are deliberately a little below the real window to leave room for the
# response and for tokenizer estimation error.
MODEL_TOKENS_LIMITS = {
    "llama-2": 3500,
    "llama2": 3500,
    "codellama": 15000,
    "llama-3": 7000,
    "llama3": 7000,
    "llama-3.1": 123000,
    "llama-3.2": 123000,
    "llama-3.3": 123000,
    "llama-4": 250000,
    "mistral": 31000,
    "mixtral": 31000,
    "ministral": 123000,
    "devstral": 123000,
    "magistral": 39000,
    "gemma": 7000,
    "gemma2": 7000,
    "gemma3": 123000,
    "phi3": 123000,
    "phi4": 15000,
    "qwen2": 31000,
    "qwen2.5": 31000,
    "qwen3": 39000,
    "deepseek-r1": 123000,
    "deepseek-v3": 123000,
    "gpt-oss": 123000,
    "granite3": 123000,
    "command-r": 123000,
    "olmo2": 3500,
    "smollm2": 7000,
    "tinyllama": 1900,
}


def get_model_tokens_limit(model: str) -> int:
    """Best-effort context window for a model name, in tokens."""
    if not model:
        return DEFAULT_TOKENS_LIMIT

    # "hf.co/user/Qwen3-8B-GGUF:Q4_K_M" -> "qwen3-8b-gguf"
    name = model.split("/")[-1].split(":")[0].lower()

    # An explicit size in the name beats the table.
    for marker, limit in (("1m", 990000), ("128k", 123000), ("100k", 98000),
                          ("64k", 63000), ("32k", 31000), ("16k", 15000), ("8k", 7000)):
        if marker in name:
            return limit

    best = None
    for prefix in MODEL_TOKENS_LIMITS:
        if name.startswith(prefix) and (best is None or len(prefix) > len(best)):
            best = prefix

    return MODEL_TOKENS_LIMITS[best] if best else DEFAULT_TOKENS_LIMIT
