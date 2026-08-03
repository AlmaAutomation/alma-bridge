"""Process exit tracking."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ExitState:
    code: Optional[int] = None
    exited: bool = False

    def set_exit(self, code: int) -> None:
        self.code = code
        self.exited = True
