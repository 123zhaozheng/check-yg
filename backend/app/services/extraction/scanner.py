# -*- coding: utf-8 -*-
"""Document scanner for discovering files to process."""

import logging
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)


class DocumentScanner:
    """Scan directories for documents to process."""

    SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".xls"}

    def __init__(self, supported_extensions: set = None):
        self.supported_extensions = supported_extensions or self.SUPPORTED_EXTENSIONS

    def scan_directory(self, directory: str, recursive: bool = True) -> List[Path]:
        """Scan directory for supported documents."""
        dir_path = Path(directory)
        if not dir_path.exists():
            raise FileNotFoundError(f"Directory not found: {directory}")
        if not dir_path.is_dir():
            raise ValueError(f"Not a directory: {directory}")

        pattern = "**/*" if recursive else "*"
        files = []

        for file_path in dir_path.glob(pattern):
            if file_path.is_file() and file_path.suffix.lower() in self.supported_extensions:
                # Skip Excel temporary files
                if file_path.name.startswith("~$"):
                    continue
                files.append(file_path)

        logger.info("Scanned %s: found %d files", directory, len(files))
        return sorted(files, key=lambda p: p.name.lower())
