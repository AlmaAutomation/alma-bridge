"""Console stderr capture."""

from __future__ import annotations

from io import StringIO


class ConsoleStderr:
    def __init__(self) -> None:
        self._buffer = StringIO()

    def write(self, data: bytes) -> int:
        text = data.decode("utf-8", errors="replace")
        self._buffer.write(text)
        return len(data)

    def getvalue(self) -> str:
        return self._buffer.getvalue()
