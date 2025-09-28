from datetime import datetime


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

DEFAULT_REPLY_PERCENT = 0.5

DEFAULT_MIN_MESSAGE_LENGTH = 2

DEFAULT_LLM_MODEL = ""

DEFAULT_GLOBAL = {
            "custom_openai_endpoint": None,
            "openai_endpoint_request_timeout": 60,
            "optout": [],
            "optin": [],
            "ratelimit_reset": datetime(1990, 1, 1, 0, 1).strftime("%Y-%m-%d %H:%M:%S"),
            "max_random_prompt_length": 200,
            "max_prompt_length": 200,
            "custom_text_prompt": None,
            "endpoint_model_history": {},
}

DEFAULT_GUILD = {
    "optin_by_default": False,
    "optin_disable_embed": False,
    "reply_percent": DEFAULT_REPLY_PERCENT,
    "messages_backread": 10,
    "messages_backread_seconds": 60 * 120,
    "messages_min_length": DEFAULT_MIN_MESSAGE_LENGTH,
    "reply_to_mentions_replies": True,
    "model": DEFAULT_LLM_MODEL,
    "custom_text_prompt": None,
    "channels_whitelist": [],
    "roles_whitelist": [],
    "members_whitelist": [],
    "public_forget": False,
    "ignore_regex": None,
    "removelist_regexes": DEFAULT_REMOVE_PATTERNS,
    "parameters": None,
    "weights": None,
    "conversation_reply_percent": 0,
    "conversation_reply_time": 20,
    "custom_model_tokens_limit": None,
    "always_reply_on_words": [],
}

DEFAULT_CHANNEL = {
    "custom_text_prompt": None,
    "reply_percent": None
}

DEFAULT_ROLE = {
    "custom_text_prompt": None,
    "reply_percent": None
}

DEFAULT_MEMBER = {
    "custom_text_prompt": None,
    "reply_percent": None
}
