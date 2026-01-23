# -*- coding: utf-8 -*-
"""
Statistics Card widget for displaying metrics
"""

from PyQt5.QtWidgets import QVBoxLayout, QLabel, QHBoxLayout, QWidget
from PyQt5.QtCore import Qt

from .card import Card
from ..styles import COLORS


class StatCard(Card):
    """
    Card for displaying a single statistic with label
    Used in dashboard/overview sections
    """
    
    def __init__(
        self, 
        title: str, 
        value: str = "0", 
        subtitle: str = "",
        color: str = "",
        parent=None
    ):
        super().__init__(parent, padding=16)
        
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet(f"""
            font-size: 13px;
            color: {COLORS['text_secondary']};
            font-weight: 500;
        """)
        
        self.value_label = QLabel(value)
        value_color = color or COLORS['text_primary']
        self.value_label.setStyleSheet(f"""
            font-size: 28px;
            font-weight: bold;
            color: {value_color};
        """)
        
        self.layout.addWidget(self.title_label)
        self.layout.addWidget(self.value_label)
        
        if subtitle:
            self.subtitle_label = QLabel(subtitle)
            self.subtitle_label.setStyleSheet(f"""
                font-size: 12px;
                color: {COLORS['text_light']};
            """)
            self.layout.addWidget(self.subtitle_label)
        
        self.layout.addStretch()
    
    def set_value(self, value: str) -> None:
        """Update the displayed value"""
        self.value_label.setText(value)
    
    def update_value(self, value: str) -> None:
        """Update the displayed value (alias for set_value)"""
        self.set_value(value)
    
    def set_color(self, color: str) -> None:
        """Update the value color"""
        self.value_label.setStyleSheet(f"""
            font-size: 28px;
            font-weight: bold;
            color: {color};
        """)


class StatCardRow(QWidget):
    """
    Horizontal row of stat cards
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(16)
        self.cards = []
    
    def add_stat(
        self, 
        title: str, 
        value: str = "0", 
        subtitle: str = "",
        color: str = ""
    ) -> StatCard:
        """Add a stat card to the row"""
        card = StatCard(title, value, subtitle, color)
        self.layout.addWidget(card)
        self.cards.append(card)
        return card
    
    def get_card(self, index: int):
        """Get card by index"""
        if 0 <= index < len(self.cards):
            return self.cards[index]
        return None
