import re

# regex patterns
URL_PATTERN = re.compile(r"(https?://\S+)")
YOUTUBE_URL_PATTERN = re.compile(r"(?:https?:\/\/)?(?:www\.)?(?:youtube\.com|youtu\.be)\/(?:watch\?v=)?(.+)")
YOUTUBE_VIDEO_ID_PATTERN = re.compile(r"(?:youtube(?:-nocookie)?\.com|youtu\.be).*(?:v=|/)([\w-]{11})")
SINGULAR_MENTION_PATTERN = re.compile(r"^<@!?&?(\d+)>$")
REGEX_RUN_TIMEOUT = 5

# "grok" trigger: a short message asking another bot to fact check something
GROK_MAX_WORDS = 25
GROK_PRIMARY_TRIGGERS = ("grok", "gork")
GROK_SECONDARY_TRIGGERS = ("true", "explain", "confirm", "real")

# Chat completion parameters the cog sets itself; users may not override them.
RESERVED_PARAMETERS = ("model", "messages", "stream")
