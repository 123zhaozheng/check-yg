# -*- coding: utf-8 -*-
"""
Progress management for long-running extraction tasks.
"""

from enum import Enum
from typing import Callable, Optional


class ProgressStatus(str, Enum):
    WAITING = "等待中"
    RUNNING = "处理中"
    COMPLETED = "已完成"
    FAILED = "失败"
    CANCELED = "已取消"


class ProgressManager:
    """
    Centralized progress reporting.

    Callback signature: (message: str, current: int, total: int)
    """

    def __init__(self) -> None:
        self._callback: Optional[Callable[[str, int, int], None]] = None
        self.status: ProgressStatus = ProgressStatus.WAITING

    def set_callback(self, callback: Callable[[str, int, int], None]) -> None:
        self._callback = callback

    def report(
        self,
        message: str,
        current: int = 0,
        total: int = 0,
        status: Optional[ProgressStatus] = None
    ) -> None:
        if status is not None:
            self.status = status
        if self._callback:
            self._callback(message, current, total)
