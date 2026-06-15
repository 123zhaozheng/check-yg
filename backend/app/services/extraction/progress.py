# -*- coding: utf-8 -*-
"""Progress tracking and reporting for extraction pipeline."""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class ProgressReport:
    """Progress report data structure."""

    task_id: str
    stage: str  # "scanning", "parsing", "classifying", "normalizing", "completed"
    current: int
    total: int
    message: str
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()

    @property
    def percentage(self) -> float:
        """Calculate progress percentage."""
        if self.total == 0:
            return 0.0
        return (self.current / self.total) * 100


class ProgressReporter:
    """Track and report extraction progress."""

    def __init__(self):
        self._callback: Optional[Callable[[ProgressReport], None]] = None
        self._current_report: Optional[ProgressReport] = None

    def set_callback(self, callback: Callable[[ProgressReport], None]) -> None:
        """Set callback function for progress updates."""
        self._callback = callback

    def report(
        self,
        task_id: str,
        stage: str,
        current: int,
        total: int,
        message: str,
    ) -> None:
        """Report progress update."""
        report = ProgressReport(
            task_id=task_id,
            stage=stage,
            current=current,
            total=total,
            message=message,
        )
        self._current_report = report

        logger.info(
            "Progress [%s] %s: %d/%d (%.1f%%) - %s",
            task_id,
            stage,
            current,
            total,
            report.percentage,
            message,
        )

        if self._callback:
            try:
                self._callback(report)
            except Exception as e:
                logger.error("Progress callback failed: %s", e)

    def get_current_report(self) -> Optional[ProgressReport]:
        """Get the most recent progress report."""
        return self._current_report
