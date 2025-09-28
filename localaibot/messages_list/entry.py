from dataclasses import dataclass
from typing import Literal, Union


@dataclass(frozen=True)
class MessageEntry:
    role: Literal['user', 'assistant', 'system', 'tool']
    content: Union[str, list]