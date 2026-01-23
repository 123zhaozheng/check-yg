# -*- coding: utf-8 -*-
"""
Document scanner module
Handles directory scanning with file priority rules
"""

import logging
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)


# File extension priority (lower number = higher priority)
EXTENSION_PRIORITY = {
    '.pdf': 1,
    '.docx': 2,
    '.doc': 3,
    '.xlsx': 4,
    '.xls': 5,
    '.txt': 6,
}

SUPPORTED_EXTENSIONS = set(EXTENSION_PRIORITY.keys())


class DocumentScanner:
    """
    Scans directories for documents with priority-based file selection
    
    Priority rule: When multiple files have the same base name,
    PDF is preferred over DOCX over Excel over TXT
    """
    
    def __init__(self, supported_extensions: Optional[Set[str]] = None):
        """
        Initialize scanner
        
        Args:
            supported_extensions: Set of supported file extensions
        """
        self.supported_extensions = supported_extensions or SUPPORTED_EXTENSIONS
    
    def scan_directory(self, directory: str, recursive: bool = True) -> List[Path]:
        """
        Scan directory for documents, applying priority rules
        
        Args:
            directory: Path to directory to scan
            recursive: Whether to scan subdirectories
            
        Returns:
            List of file paths to process (after priority filtering)
        """
        dir_path = Path(directory)
        if not dir_path.exists():
            raise FileNotFoundError(f"Directory not found: {directory}")
        
        if not dir_path.is_dir():
            raise ValueError(f"Not a directory: {directory}")
        
        # Collect all matching files
        all_files: List[Path] = []
        
        if recursive:
            pattern = '**/*'
        else:
            pattern = '*'
        
        for file_path in dir_path.glob(pattern):
            if file_path.is_file() and file_path.suffix.lower() in self.supported_extensions:
                # 跳过 Excel 临时文件（~$ 开头）
                if file_path.name.startswith('~$'):
                    continue
                all_files.append(file_path)
        
        # Group by base name (without extension)
        grouped = self._group_by_basename(all_files)
        
        # Select highest priority file from each group
        selected = self._select_by_priority(grouped)
        
        logger.info(
            "Scanned %s: found %d files, selected %d after priority filtering",
            directory, len(all_files), len(selected)
        )
        
        return sorted(selected, key=lambda p: p.name.lower())
    
    def _group_by_basename(self, files: List[Path]) -> Dict[str, List[Path]]:
        """Group files by their base name (stem)"""
        grouped: Dict[str, List[Path]] = defaultdict(list)
        
        for file_path in files:
            # Use parent + stem as key to handle same names in different dirs
            key = str(file_path.parent / file_path.stem)
            grouped[key].append(file_path)
        
        return grouped
    
    def _select_by_priority(self, grouped: Dict[str, List[Path]]) -> List[Path]:
        """Select highest priority file from each group"""
        selected = []
        
        for base_name, files in grouped.items():
            if len(files) == 1:
                selected.append(files[0])
            else:
                # Sort by priority and select first
                files.sort(key=lambda f: EXTENSION_PRIORITY.get(f.suffix.lower(), 99))
                selected.append(files[0])
                
                # Log skipped files
                skipped = files[1:]
                if skipped:
                    logger.debug(
                        "Selected %s, skipped: %s",
                        files[0].name,
                        [f.name for f in skipped]
                    )
        
        return selected
    
    def get_file_info(self, file_path: Path) -> Dict:
        """
        Get file information
        
        Args:
            file_path: Path to file
            
        Returns:
            Dict with file info (name, size, extension, etc.)
        """
        stat = file_path.stat()
        return {
            'name': file_path.name,
            'path': str(file_path),
            'extension': file_path.suffix.lower(),
            'size': stat.st_size,
            'size_human': self._format_size(stat.st_size),
        }
    
    @staticmethod
    def _format_size(size: int) -> str:
        """Format file size in human readable format"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"
