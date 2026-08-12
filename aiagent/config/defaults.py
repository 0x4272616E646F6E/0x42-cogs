DEFAULT_PROMPT = "You are {botname}. You are in a Discord text channel. \
Respond to anything, including URLs, helpfully in a short message. \
Fulfill your persona and don't speak in third person. \
You are forbidden from saying you're an AI or a bot."

DEFAULT_REMOVE_PATTERNS = [
    r'<think>[\s\S]*?<\/think>',  # for thinking LLMs
    r'^As an AI language model,?',
    r'^(User )?"?{botname}"? (said|says|respond(ed|s)|replie[ds])( to [^":]+)?:?',
    r'^As "?{botname}"?, (I|you)( might| would| could)? (respond|reply|say)( with)?( something like)?:?',
    r'^You respond as "?{botname}"?:',
    r'^[<({{\[]{botname}[>)}}\]]',  # [name], {name}, <name>, (name)
    r'^{botname}:',
    r'^(User )?"?{authorname}"? (said|says|respond(ed|s)|replie[ds])( to [^":]+)?:?',
    r'^As "?{authorname}"?, (I|you)( might| would| could)? (respond|reply|say)( with)?( something like)?:?',
    r'^You respond as "?{authorname}"?:',
    r'^[<({{\[]{authorname}[>)}}\]]',  # [name], {name}, <name>, (name)
    r'^{authorname}:',
    r'\n*\[Image[^\]]+\]'
]

DEFAULT_MIN_MESSAGE_LENGTH = 2

DEFAULT_LLM_MODEL = ""

# Ollama's OpenAI-compatible API on the same host as the bot.
DEFAULT_ENDPOINT = "http://localhost:11434/v1"

# Fallback context window (in tokens) when a model isn't recognised.
DEFAULT_TOKENS_LIMIT = 7000

DEFAULT_GLOBAL = {
    "llm_endpoint": DEFAULT_ENDPOINT,
    "llm_endpoint_request_timeout": 60,
    "optout": [],
    "optin": [],
    "max_prompt_length": 200,
    "custom_text_prompt": None,
    "endpoint_model_history": {},
}

DEFAULT_GUILD = {
    "optin_by_default": False,
    "optin_disable_embed": False,
    "messages_backread": 10,
    "messages_backread_seconds": 60 * 120,
    "messages_min_length": DEFAULT_MIN_MESSAGE_LENGTH,
    "model": DEFAULT_LLM_MODEL,
    "custom_text_prompt": None,
    "presets": "{}",
    "channels_whitelist": [],
    "roles_whitelist": [],
    "members_whitelist": [],
    "public_forget": False,
    "ignore_regex": None,
    "removelist_regexes": DEFAULT_REMOVE_PATTERNS,
    "parameters": None,
    "custom_model_tokens_limit": None,
}

DEFAULT_CHANNEL = {
    "custom_text_prompt": None,
}

DEFAULT_ROLE = {
    "custom_text_prompt": None,
}

DEFAULT_MEMBER = {
    "custom_text_prompt": None,
}
