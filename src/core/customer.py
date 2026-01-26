# -*- coding: utf-8 -*-
"""
Customer name list management module
Handles importing and managing customer names from Excel files
"""

import logging
from pathlib import Path
from typing import List, Optional, Set

import openpyxl

logger = logging.getLogger(__name__)


class CustomerManager:
    """Manages customer name list for audit matching"""
    
    def __init__(self):
        self._customers: List[str] = []
        self._customer_set: Set[str] = set()
        self._source_file: Optional[Path] = None
    
    def load_from_excel(self, file_path: str) -> int:
        """
        Load customer names from Excel file (first column)
        
        Args:
            file_path: Path to Excel file (.xlsx or .xls)
            
        Returns:
            Number of unique customers loaded
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        ext = path.suffix.lower()
        if ext not in ('.xlsx', '.xls'):
            raise ValueError(f"Unsupported file format: {ext}")
        
        try:
            wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
            ws = wb.active
            
            names = []
            for row in ws.iter_rows(min_col=1, max_col=1, values_only=True):
                cell_value = row[0]
                if cell_value is not None:
                    name = str(cell_value).strip()
                    if name and name not in self._customer_set:
                        names.append(name)
                        self._customer_set.add(name)
            
            wb.close()
            
            self._customers.extend(names)
            self._source_file = path
            
            logger.info("Loaded %d unique customers from %s", len(names), path.name)
            return len(names)
            
        except Exception as e:
            logger.error("Failed to load Excel file: %s", e)
            raise

    def load_from_list(self, names: List[str]) -> int:
        """
        Load customer names from a list, replacing existing data.

        Args:
            names: List of customer names

        Returns:
            Number of unique customers loaded
        """
        self.clear()
        added = 0
        for name in names:
            clean = str(name).strip()
            if clean and clean not in self._customer_set:
                self._customers.append(clean)
                self._customer_set.add(clean)
                added += 1
        return added
    
    def add_customer(self, name: str) -> bool:
        """
        Add a single customer name
        
        Args:
            name: Customer name to add
            
        Returns:
            True if added, False if already exists
        """
        name = name.strip()
        if not name or name in self._customer_set:
            return False
        
        self._customers.append(name)
        self._customer_set.add(name)
        return True
    
    def remove_customer(self, name: str) -> bool:
        """
        Remove a customer name
        
        Args:
            name: Customer name to remove
            
        Returns:
            True if removed, False if not found
        """
        name = name.strip()
        if name not in self._customer_set:
            return False
        
        self._customers.remove(name)
        self._customer_set.remove(name)
        return True
    
    def clear(self) -> None:
        """Clear all customer names"""
        self._customers.clear()
        self._customer_set.clear()
        self._source_file = None
    
    @property
    def customers(self) -> List[str]:
        """Get list of all customer names"""
        return self._customers.copy()
    
    @property
    def count(self) -> int:
        """Get number of customers"""
        return len(self._customers)
    
    @property
    def source_file(self) -> Optional[Path]:
        """Get source file path"""
        return self._source_file
    
    def __contains__(self, name: str) -> bool:
        return name in self._customer_set
    
    def __len__(self) -> int:
        return len(self._customers)
    
    def __iter__(self):
        return iter(self._customers)
