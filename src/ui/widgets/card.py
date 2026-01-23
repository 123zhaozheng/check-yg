# -*- coding: utf-8 -*-
"""
Base Card widget - foundation for card-based UI
"""

from PyQt5.QtWidgets import QFrame, QVBoxLayout, QLabel, QGraphicsDropShadowEffect
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor


class Card(QFrame):
    """
    Base card widget with shadow and rounded corners
    Apple-inspired minimalist design
    """
    
    def __init__(self, parent=None, padding: int = 20):
        super().__init__(parent)
        self.setObjectName("card")
        self._setup_style(padding)
        self._setup_shadow()
        
        # Main layout
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(padding, padding, padding, padding)
        self.layout.setSpacing(12)
    
    def _setup_style(self, padding: int) -> None:
        """Setup card styling"""
        self.setStyleSheet("""
            QFrame#card {
                background-color: #FFFFFF;
                border-radius: 12px;
                border: 1px solid #F3F4F6;
            }
        """)
    
    def _setup_shadow(self) -> None:
        """Add subtle drop shadow"""
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setXOffset(0)
        shadow.setYOffset(4)
        shadow.setColor(QColor(0, 0, 0, 25))
        self.setGraphicsEffect(shadow)
    
    def add_title(self, text: str) -> QLabel:
        """Add a title label to the card"""
        title = QLabel(text)
        title.setObjectName("section_title")
        title.setStyleSheet("""
            font-size: 16px;
            font-weight: 600;
            color: #1F2937;
            margin-bottom: 8px;
        """)
        self.layout.insertWidget(0, title)
        return title
    
    def add_subtitle(self, text: str) -> QLabel:
        """Add a subtitle/description label"""
        subtitle = QLabel(text)
        subtitle.setObjectName("subtitle")
        subtitle.setStyleSheet("""
            font-size: 13px;
            color: #6B7280;
        """)
        subtitle.setWordWrap(True)
        self.layout.addWidget(subtitle)
        return subtitle
