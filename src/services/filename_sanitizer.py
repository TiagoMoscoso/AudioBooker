"""Sanitizes strings for safe use as file/directory names on both Windows and
Linux (§44): strips path-traversal sequences, invalid characters, and
reserved Windows device names."""
from __future__ import annotations

import re

_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED_WINDOWS_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
_MAX_LENGTH = 150


class FilenameSanitizer:
    def sanitize(self, name: str, fallback: str = "arquivo") -> str:
        name = name.strip()
        name = name.replace("..", "_")
        name = _INVALID_CHARS.sub("_", name)
        name = re.sub(r"\s+", " ", name).strip(" .")
        if not name:
            name = fallback

        base = name.split(".")[0].upper()
        if base in _RESERVED_WINDOWS_NAMES:
            name = f"_{name}"

        if len(name) > _MAX_LENGTH:
            name = name[:_MAX_LENGTH].rstrip()

        return name or fallback
