import re

# regex patterns
URL_PATTERN = re.compile(r"(https?://\S+)")
SINGULAR_MENTION_PATTERN = re.compile(r"^<@!?&?(\d+)>$")

# Chat completion parameters the cog sets itself; users may not override them.
RESERVED_PARAMETERS = ("model", "messages", "stream")
