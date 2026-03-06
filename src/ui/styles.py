# -*- coding: utf-8 -*-
"""
UI Styles and Theme definitions
Clean minimalist design with light sidebar
"""

# Color Palette - Light theme inspired by reference
COLORS = {
    'primary': '#3B82F6',       # Blue - buttons, links, active state
    'primary_hover': '#2563EB',
    'primary_pressed': '#1D4ED8',
    'primary_light': '#EBF5FF',
    
    'danger': '#EF4444',        # Red - high risk
    'danger_light': '#FEE2E2',
    
    'warning': '#F59E0B',       # Yellow/Orange - medium risk
    'warning_light': '#FEF3C7',
    
    'success': '#10B981',       # Green - low risk, success
    'success_light': '#D1FAE5',
    
    'background': '#FFFFFF',    # White - main background
    'card': '#FFFFFF',          # White - card background
    'sidebar': '#FAFBFC',       # Very light gray - sidebar
    'sidebar_hover': '#F3F4F6',
    'sidebar_active': '#EBF5FF',
    'sidebar_border': '#E5E7EB',
    
    'text_primary': '#1F2937',
    'text_secondary': '#6B7280',
    'text_light': '#9CA3AF',
    'text_white': '#FFFFFF',
    
    'border': '#E5E7EB',
    'border_light': '#F3F4F6',
}

# Main Application Style
MAIN_STYLE = """
QMainWindow {
    background-color: %(background)s;
}

QWidget {
    font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
    font-size: 13px;
    color: %(text_primary)s;
}

/* Sidebar Navigation - Light theme */
#sidebar {
    background-color: %(sidebar)s;
    border-right: 1px solid %(sidebar_border)s;
}

#sidebar QPushButton.nav_btn {
    background-color: transparent;
    color: %(text_secondary)s;
    border: none;
    border-radius: 6px;
    padding: 10px 16px;
    text-align: left;
    font-size: 13px;
    font-weight: 500;
    min-height: 36px;
}

#sidebar QPushButton.nav_btn:hover {
    background-color: %(sidebar_hover)s;
    color: %(text_primary)s;
}

#sidebar QPushButton.nav_btn:checked {
    background-color: %(sidebar_active)s;
    color: %(primary)s;
    font-weight: 600;
}

#sidebar_title {
    color: %(text_primary)s;
    font-size: 15px;
    font-weight: bold;
}

#sidebar_subtitle {
    color: %(text_light)s;
    font-size: 11px;
}

/* Settings button at bottom */
#settings_btn {
    background-color: transparent;
    border: none;
    border-radius: 6px;
    padding: 8px;
    color: %(text_secondary)s;
}

#settings_btn:hover {
    background-color: %(sidebar_hover)s;
    color: %(text_primary)s;
}

/* Content Area */
#content_area {
    background-color: %(background)s;
}

/* Cards */
QFrame#card {
    background-color: %(card)s;
    border-radius: 8px;
    border: 1px solid %(border_light)s;
}

/* Primary Button */
QPushButton#primary_btn {
    background-color: %(primary)s;
    color: %(text_white)s;
    border: none;
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: 500;
    font-size: 13px;
    min-width: 80px;
    min-height: 32px;
}

QPushButton#primary_btn:hover {
    background-color: %(primary_hover)s;
}

QPushButton#primary_btn:pressed {
    background-color: %(primary_pressed)s;
}

QPushButton#primary_btn:disabled {
    background-color: %(text_light)s;
}

/* Secondary Button */
QPushButton#secondary_btn {
    background-color: %(card)s;
    color: %(text_primary)s;
    border: 1px solid %(border)s;
    border-radius: 6px;
    padding: 8px 16px;
    font-size: 13px;
    min-width: 80px;
    min-height: 32px;
}

QPushButton#secondary_btn:hover {
    background-color: %(sidebar_hover)s;
    border-color: %(text_light)s;
}

/* Danger Button */
QPushButton#danger_btn {
    background-color: %(danger)s;
    color: %(text_white)s;
    border: none;
    border-radius: 6px;
    padding: 8px 16px;
    font-size: 13px;
    min-width: 80px;
    min-height: 32px;
}

QPushButton#danger_btn:hover {
    background-color: #DC2626;
}

/* Input Fields */
QLineEdit, QTextEdit {
    background-color: %(card)s;
    border: 1px solid %(border)s;
    border-radius: 6px;
    padding: 8px 12px;
    color: %(text_primary)s;
    font-size: 13px;
    min-height: 20px;
}

QLineEdit:focus, QTextEdit:focus {
    border-color: %(primary)s;
}

QLineEdit:disabled {
    background-color: %(sidebar)s;
    color: %(text_secondary)s;
}

/* Labels */
QLabel#title {
    font-size: 20px;
    font-weight: bold;
    color: %(text_primary)s;
}

QLabel#subtitle {
    font-size: 13px;
    color: %(text_secondary)s;
}

QLabel#section_title {
    font-size: 14px;
    font-weight: 600;
    color: %(text_primary)s;
}

/* Tables */
QTableWidget {
    background-color: %(card)s;
    border: 1px solid %(border_light)s;
    border-radius: 6px;
    gridline-color: %(border_light)s;
    font-size: 12px;
}

QTableWidget::item {
    padding: 6px 8px;
}

QTableWidget::item:selected {
    background-color: %(primary)s;
    color: %(text_white)s;
}

QHeaderView::section {
    background-color: %(sidebar)s;
    color: %(text_primary)s;
    font-weight: 600;
    font-size: 12px;
    padding: 8px;
    border: none;
    border-bottom: 1px solid %(border)s;
}

/* Scroll Bars */
QScrollBar:vertical {
    background-color: transparent;
    width: 8px;
    margin: 0;
}

QScrollBar::handle:vertical {
    background-color: %(border)s;
    border-radius: 4px;
    min-height: 30px;
}

QScrollBar::handle:vertical:hover {
    background-color: %(text_light)s;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: none;
}

/* Progress Bar */
QProgressBar {
    background-color: %(border_light)s;
    border: none;
    border-radius: 4px;
    height: 6px;
    text-align: center;
}

QProgressBar::chunk {
    background-color: %(primary)s;
    border-radius: 4px;
}

/* List Widget */
QListWidget {
    background-color: %(card)s;
    border: 1px solid %(border)s;
    border-radius: 6px;
    padding: 4px;
    font-size: 13px;
}

QListWidget::item {
    padding: 6px 10px;
    border-radius: 4px;
}

QListWidget::item:selected {
    background-color: %(primary)s;
    color: %(text_white)s;
}

QListWidget::item:hover:!selected {
    background-color: %(sidebar_hover)s;
}

/* Combo Box */
QComboBox {
    background-color: %(card)s;
    border: 1px solid %(border)s;
    border-radius: 6px;
    padding: 6px 10px;
    min-width: 100px;
    font-size: 13px;
}

QComboBox:hover {
    border-color: %(primary)s;
}

QComboBox::drop-down {
    border: none;
    width: 20px;
}

QComboBox QAbstractItemView {
    background-color: %(card)s;
    border: 1px solid %(border)s;
    border-radius: 6px;
    selection-background-color: %(primary)s;
}

/* Check Box */
QCheckBox {
    spacing: 8px;
    font-size: 13px;
}

QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid %(border)s;
    border-radius: 4px;
    background-color: %(card)s;
}

QCheckBox::indicator:checked {
    background-color: %(primary)s;
    border-color: %(primary)s;
}

/* Dialog */
QDialog {
    background-color: %(background)s;
}

QDialog QLabel {
    font-size: 13px;
}

/* Group Box */
QGroupBox {
    font-size: 13px;
    font-weight: 600;
    color: %(text_primary)s;
    border: 1px solid %(border)s;
    border-radius: 6px;
    margin-top: 12px;
    padding-top: 12px;
}

QGroupBox::title {
subcontrol-origin: margin;
left: 12px;
padding: 0 6px;
}
""" % COLORS

# Settings Dialog Style
SETTINGS_DIALOG_STYLE = """
QTabWidget::pane {
border: 1px solid %(border)s;
border-radius: 6px;
background-color: %(card)s;
}

QTabBar::tab {
background-color: %(sidebar_hover)s;
color: %(text_secondary)s;
padding: 10px 20px;
margin-right: 2px;
border-top-left-radius: 6px;
border-top-right-radius: 6px;
font-size: 13px;
}

QTabBar::tab:selected {
background-color: %(card)s;
color: %(text_primary)s;
font-weight: bold;
}

QTabBar::tab:hover:!selected {
background-color: %(border)s;
}

/* Settings button styles */
QPushButton#settings_cancel_btn {
background-color: %(card)s;
color: %(text_primary)s;
border: 1px solid %(border)s;
border-radius: 6px;
font-size: 13px;
}

QPushButton#settings_cancel_btn:hover {
background-color: %(sidebar_hover)s;
}

QPushButton#settings_save_btn {
background-color: %(primary)s;
color: %(text_white)s;
border: none;
border-radius: 6px;
font-size: 13px;
font-weight: 500;
}

QPushButton#settings_save_btn:hover {
background-color: %(primary_hover)s;
}

/* Input fields in settings */
QLineEdit#settings_input, QSpinBox#settings_input {
background-color: %(card)s;
border: 1px solid %(border)s;
border-radius: 6px;
padding-left: 12px;
padding-right: 12px;
font-size: 13px;
color: %(text_primary)s;
}

QLineEdit#settings_input:focus, QSpinBox#settings_input:focus {
border: 1px solid %(primary)s;
}

/* Labels in settings */
QLabel#settings_title {
font-size: 15px;
font-weight: bold;
color: %(text_primary)s;
}

QLabel#settings_label {
font-size: 13px;
color: %(text_secondary)s;
}

QLabel#settings_desc {
font-size: 11px;
color: %(text_light)s;
}
""" % COLORS

def get_risk_style(risk_level: str) -> str:
    """Get background color style for risk level"""
    if "高" in risk_level:
        return f"background-color: {COLORS['danger_light']}; color: {COLORS['danger']};"
    elif "中" in risk_level:
        return f"background-color: {COLORS['warning_light']}; color: {COLORS['warning']};"
    else:
        return f"background-color: {COLORS['success_light']}; color: {COLORS['success']};"


def get_confidence_style(confidence: str) -> str:
    """Get style for confidence level"""
    if "精确" in confidence:
        return f"color: {COLORS['success']}; font-weight: bold;"
    elif "脱敏" in confidence:
        return f"color: {COLORS['warning']}; font-weight: bold;"
    else:
        return f"color: {COLORS['danger']}; font-weight: bold;"
