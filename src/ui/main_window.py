# -*- coding: utf-8 -*-
"""
Main window - application shell with light sidebar navigation
"""

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QPushButton, QLabel, QStackedWidget, QFrame,
    QDialog, QLineEdit, QSpinBox,
    QTabWidget
)
from PyQt5.QtCore import Qt

from .styles import MAIN_STYLE, COLORS
from .pages import ResultPage, ExtractPage, ReviewPage
from ..config import get_config


class SettingsDialog(QDialog):
    """Settings dialog for MinerU and LLM configuration"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.config = get_config()
        self.setWindowTitle("设置")
        self.setMinimumSize(600, 650)
        self.setMaximumSize(700, 800)
        
        # 清除父窗口样式的影响，设置独立样式
        self.setStyleSheet("")
        
        self._setup_ui()
        self._load_config()
    
    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(16)
        main_layout.setContentsMargins(20, 20, 20, 20)
        
        # 使用 Tab 页面组织配置
        self.tab_widget = QTabWidget()
        self.tab_widget.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #E5E7EB;
                border-radius: 6px;
                background-color: #FFFFFF;
            }
            QTabBar::tab {
                background-color: #F3F4F6;
                color: #6B7280;
                padding: 10px 20px;
                margin-right: 2px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                font-size: 13px;
            }
            QTabBar::tab:selected {
                background-color: #FFFFFF;
                color: #1F2937;
                font-weight: bold;
            }
            QTabBar::tab:hover:!selected {
                background-color: #E5E7EB;
            }
        """)
        
        # 基础设置 Tab
        basic_tab = self._create_basic_tab()
        self.tab_widget.addTab(basic_tab, "基础设置")
        
        # AI 高级设置 Tab
        ai_tab = self._create_ai_tab()
        self.tab_widget.addTab(ai_tab, "AI 高级设置")
        
        main_layout.addWidget(self.tab_widget, 1)
        
        # ========== 按钮区域 ==========
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)
        btn_layout.addStretch()
        
        cancel_btn = QPushButton("取消")
        cancel_btn.setFixedSize(80, 38)
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #FFFFFF;
                color: #1F2937;
                border: 1px solid #E5E7EB;
                border-radius: 6px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #F3F4F6;
            }
        """)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        
        save_btn = QPushButton("保存")
        save_btn.setFixedSize(80, 38)
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.setStyleSheet("""
            QPushButton {
                background-color: #3B82F6;
                color: #FFFFFF;
                border: none;
                border-radius: 6px;
                font-size: 13px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #2563EB;
            }
        """)
        save_btn.clicked.connect(self._save_and_close)
        btn_layout.addWidget(save_btn)
        
        main_layout.addLayout(btn_layout)
    
    def _create_basic_tab(self) -> QWidget:
        """创建基础设置 Tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # ========== MinerU 区域 ==========
        mineru_title = QLabel("MinerU PDF解析服务")
        mineru_title.setStyleSheet("font-size: 15px; font-weight: bold; color: #1F2937;")
        layout.addWidget(mineru_title)
        
        mineru_url_label = QLabel("服务地址")
        mineru_url_label.setStyleSheet("font-size: 13px; color: #6B7280;")
        layout.addWidget(mineru_url_label)
        
        self.mineru_url_input = QLineEdit()
        self.mineru_url_input.setPlaceholderText("http://localhost:8000")
        self.mineru_url_input.setFixedHeight(40)
        self.mineru_url_input.setStyleSheet(self._input_style())
        layout.addWidget(self.mineru_url_input)
        
        # 分隔线
        layout.addWidget(self._create_separator())
        
        # ========== LLM 基础配置 ==========
        llm_title = QLabel("大模型 API 配置")
        llm_title.setStyleSheet("font-size: 15px; font-weight: bold; color: #1F2937;")
        layout.addWidget(llm_title)
        
        # API 地址
        llm_url_label = QLabel("API 地址")
        llm_url_label.setStyleSheet("font-size: 13px; color: #6B7280; margin-top: 8px;")
        layout.addWidget(llm_url_label)
        
        self.llm_url_input = QLineEdit()
        self.llm_url_input.setPlaceholderText("https://api.openai.com/v1")
        self.llm_url_input.setFixedHeight(40)
        self.llm_url_input.setStyleSheet(self._input_style())
        layout.addWidget(self.llm_url_input)
        
        # 模型名称
        llm_model_label = QLabel("模型名称")
        llm_model_label.setStyleSheet("font-size: 13px; color: #6B7280; margin-top: 8px;")
        layout.addWidget(llm_model_label)
        
        self.llm_model_input = QLineEdit()
        self.llm_model_input.setPlaceholderText("gpt-4")
        self.llm_model_input.setFixedHeight(40)
        self.llm_model_input.setStyleSheet(self._input_style())
        layout.addWidget(self.llm_model_input)
        
        # API Key
        llm_key_label = QLabel("API Key")
        llm_key_label.setStyleSheet("font-size: 13px; color: #6B7280; margin-top: 8px;")
        layout.addWidget(llm_key_label)
        
        self.llm_key_input = QLineEdit()
        self.llm_key_input.setPlaceholderText("sk-...")
        self.llm_key_input.setEchoMode(QLineEdit.Password)
        self.llm_key_input.setFixedHeight(40)
        self.llm_key_input.setStyleSheet(self._input_style())
        layout.addWidget(self.llm_key_input)
        
        layout.addStretch()
        return widget
    
    def _create_ai_tab(self) -> QWidget:
        """创建 AI 高级设置 Tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # ========== 流水提取设置 ==========
        extract_title = QLabel("流水提取设置")
        extract_title.setStyleSheet("font-size: 15px; font-weight: bold; color: #1F2937;")
        layout.addWidget(extract_title)
        
        extract_row = QHBoxLayout()
        extract_row.setSpacing(20)
        
        # 每次给AI行数
        flow_batch_layout = QVBoxLayout()
        flow_batch_label = QLabel("每次给AI行数")
        flow_batch_label.setStyleSheet("font-size: 13px; color: #6B7280;")
        flow_batch_layout.addWidget(flow_batch_label)
        
        flow_batch_desc = QLabel("标准化阶段每次发送的行数")
        flow_batch_desc.setStyleSheet("font-size: 11px; color: #9CA3AF;")
        flow_batch_layout.addWidget(flow_batch_desc)
        
        self.flow_batch_spin = QSpinBox()
        self.flow_batch_spin.setRange(1, 100)
        self.flow_batch_spin.setValue(20)
        self.flow_batch_spin.setFixedHeight(40)
        self.flow_batch_spin.setStyleSheet("""
            QSpinBox {
                background-color: #FFFFFF;
                border: 1px solid #E5E7EB;
                border-radius: 6px;
                padding-left: 12px;
                font-size: 13px;
                color: #1F2937;
            }
            QSpinBox:focus {
                border: 1px solid #3B82F6;
            }
            QSpinBox::up-button, QSpinBox::down-button {
                width: 24px;
            }
        """)
        flow_batch_layout.addWidget(self.flow_batch_spin)
        extract_row.addLayout(flow_batch_layout)
        
        # 表格置信度阈值
        flow_threshold_layout = QVBoxLayout()
        flow_threshold_label = QLabel("表格置信度阈值")
        flow_threshold_label.setStyleSheet("font-size: 13px; color: #6B7280;")
        flow_threshold_layout.addWidget(flow_threshold_label)
        
        flow_threshold_desc = QLabel("高于此值才认定为流水表格")
        flow_threshold_desc.setStyleSheet("font-size: 11px; color: #9CA3AF;")
        flow_threshold_layout.addWidget(flow_threshold_desc)
        
        self.flow_threshold_spin = QSpinBox()
        self.flow_threshold_spin.setRange(0, 100)
        self.flow_threshold_spin.setValue(70)
        self.flow_threshold_spin.setSuffix(" 分")
        self.flow_threshold_spin.setFixedHeight(40)
        self.flow_threshold_spin.setStyleSheet("""
            QSpinBox {
                background-color: #FFFFFF;
                border: 1px solid #E5E7EB;
                border-radius: 6px;
                padding-left: 12px;
                font-size: 13px;
                color: #1F2937;
            }
            QSpinBox:focus {
                border: 1px solid #3B82F6;
            }
            QSpinBox::up-button, QSpinBox::down-button {
                width: 24px;
            }
        """)
        flow_threshold_layout.addWidget(self.flow_threshold_spin)
        extract_row.addLayout(flow_threshold_layout)
        
        layout.addLayout(extract_row)
        
        return widget
    
    def _input_style(self) -> str:
        """返回输入框的通用样式"""
        return """
            QLineEdit {
                background-color: #FFFFFF;
                border: 1px solid #E5E7EB;
                border-radius: 6px;
                padding-left: 12px;
                padding-right: 12px;
                font-size: 13px;
                color: #1F2937;
            }
            QLineEdit:focus {
                border: 1px solid #3B82F6;
            }
        """
    
    def _create_separator(self) -> QFrame:
        """创建分隔线"""
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFixedHeight(1)
        separator.setStyleSheet("background-color: #E5E7EB; margin: 8px 0;")
        return separator
    
    def _load_config(self):
        self.mineru_url_input.setText(self.config.mineru_url)
        self.llm_url_input.setText(self.config.llm_url)
        self.llm_model_input.setText(self.config.llm_model)
        self.llm_key_input.setText(self.config.llm_api_key)
        self.flow_batch_spin.setValue(self.config.flow_batch_size)
        self.flow_threshold_spin.setValue(self.config.flow_confidence_threshold)
    
    def _save_and_close(self):
        self.config.set('mineru.url', self.mineru_url_input.text().strip() or 'http://localhost:8000')
        self.config.set('llm.url', self.llm_url_input.text().strip() or 'https://api.openai.com/v1')
        self.config.set('llm.model', self.llm_model_input.text().strip() or 'gpt-4')
        self.config.set('llm.api_key', self.llm_key_input.text())
        self.config.set('flow_extraction.batch_size', self.flow_batch_spin.value())
        self.config.set('flow_extraction.confidence_threshold', self.flow_threshold_spin.value())
        self.config.save()
        self.accept()


class MainWindow(QMainWindow):
    """Main application window with light sidebar navigation"""
    
    # 页面索引常量
    PAGE_EXTRACT = 0   # 流水提取页
    PAGE_PREVIEW = 1   # 流水预览页
    PAGE_REVIEW = 2    # 审查配置页
    PAGE_RESULT = 3    # 结果展示页
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("员工-客户金额往来审计系统")
        self.setMinimumSize(1100, 700)
        self.resize(1280, 800)
        self.setStyleSheet(MAIN_STYLE)
        self._setup_ui()
        self._connect_signals()
    
    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        sidebar = self._create_sidebar()
        main_layout.addWidget(sidebar)
        
        content_area = QWidget()
        content_area.setObjectName("content_area")
        content_layout = QVBoxLayout(content_area)
        content_layout.setContentsMargins(32, 28, 32, 28)
        
        self.page_stack = QStackedWidget()
        
        # 创建页面实例
        self.extract_page = ExtractPage()
        from .pages.preview_page import PreviewPage
        self.preview_page = PreviewPage()
        self.review_page = ReviewPage()
        self.result_page = ResultPage()
        
        # 按顺序添加页面
        self.page_stack.addWidget(self.extract_page)   # 索引 0
        self.page_stack.addWidget(self.preview_page)   # 索引 1
        self.page_stack.addWidget(self.review_page)    # 索引 2
        self.page_stack.addWidget(self.result_page)    # 索引 3
        
        content_layout.addWidget(self.page_stack)
        main_layout.addWidget(content_area, 1)
    
    def _create_sidebar(self) -> QWidget:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(200)
        
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(12, 16, 12, 16)
        layout.setSpacing(0)
        
        title = QLabel("审计系统")
        title.setStyleSheet(f"""
            color: {COLORS['text_primary']};
            font-size: 16px;
            font-weight: bold;
            padding: 8px 8px 4px 8px;
        """)
        layout.addWidget(title)
        
        subtitle = QLabel("员工-客户金额往来")
        subtitle.setStyleSheet(f"""
            color: {COLORS['text_light']};
            font-size: 11px;
            padding: 0 8px 16px 8px;
        """)
        layout.addWidget(subtitle)
        
        self.nav_buttons = []
        nav_items = [
            ("📥  流水", "提取银行流水", self.PAGE_EXTRACT),
            ("📋  预览", "查看流水数据", self.PAGE_PREVIEW),
            ("🔍  审查", "匹配客户名单", self.PAGE_REVIEW),
            ("📊  结果", "查看审查结果", self.PAGE_RESULT),
        ]
        
        for text, tooltip, page_idx in nav_items:
            btn = QPushButton(text)
            btn.setToolTip(tooltip)
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent;
                    color: {COLORS['text_secondary']};
                    border: none;
                    border-radius: 6px;
                    padding: 10px 12px;
                    text-align: left;
                    font-size: 13px;
                    font-weight: 500;
                    min-height: 36px;
                }}
                QPushButton:hover {{
                    background-color: {COLORS['sidebar_hover']};
                    color: {COLORS['text_primary']};
                }}
                QPushButton:checked {{
                    background-color: {COLORS['sidebar_active']};
                    color: {COLORS['primary']};
                    font-weight: 600;
                }}
            """)
            btn.clicked.connect(lambda checked, idx=page_idx: self._switch_page(idx))
            layout.addWidget(btn)
            self.nav_buttons.append(btn)
        
        self.nav_buttons[0].setChecked(True)
        
        layout.addStretch()
        
        settings_btn = QPushButton("⚙️  设置")
        settings_btn.setCursor(Qt.PointingHandCursor)
        settings_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: none;
                border-radius: 6px;
                padding: 10px 12px;
                text-align: left;
                font-size: 13px;
                color: {COLORS['text_secondary']};
                min-height: 36px;
            }}
            QPushButton:hover {{
                background-color: {COLORS['sidebar_hover']};
                color: {COLORS['text_primary']};
            }}
        """)
        settings_btn.clicked.connect(self._show_settings)
        layout.addWidget(settings_btn)
        
        version_label = QLabel("v1.0.0")
        version_label.setStyleSheet(f"""
            color: {COLORS['text_light']};
            font-size: 10px;
            padding: 8px;
        """)
        layout.addWidget(version_label)
        
        return sidebar
    
    def _connect_signals(self):
        # ExtractPage -> PreviewPage (flow extraction complete)
        self.extract_page.extraction_completed.connect(self._on_extraction_complete)
        
        # ReviewPage -> ResultPage (review complete)
        self.review_page.start_review.connect(self._on_review_start)
        
        # ResultPage -> ExtractPage (new review)
        self.result_page.new_audit_btn.clicked.connect(
            lambda: self._switch_page(self.PAGE_EXTRACT)
        )
    
    def _switch_page(self, page_index: int) -> None:
        """
        切换到指定页面
        
        Args:
            page_index: 页面索引
                0 - ExtractPage (流水提取)
                1 - PreviewPage (流水预览)
                2 - ReviewPage (审查配置)
                3 - ResultPage (结果展示)
        """
        # 切换页面栈
        self.page_stack.setCurrentIndex(page_index)
        
        # 更新导航按钮状态
        for i, btn in enumerate(self.nav_buttons):
            btn.setChecked(i == page_index)
    
    def _show_settings(self) -> None:
        """显示设置对话框"""
        dialog = SettingsDialog(self)
        dialog.exec_()
    
    def _on_extraction_complete(self, result):
        """
        处理流水提取完成
        1. 切换到预览页面
        2. 传递提取结果
        """
        # 传递结果到预览页面
        self.preview_page.set_extraction_result(result)
        # 切换到预览页面
        self._switch_page(self.PAGE_PREVIEW)
    
    def _on_review_start(self, flow_excel_path: str, customers: list):
        """
        处理审查开始
        执行审查并切换到结果页面
        """
        try:
            from ..core.reviewer import Reviewer
            reviewer = Reviewer()
            result = reviewer.run_review(flow_excel_path, customers=customers)
            
            # 传递结果到结果页面
            if hasattr(self.result_page, 'set_review_result'):
                self.result_page.set_review_result(result)
            
            # 切换到结果页面
            self._switch_page(self.PAGE_RESULT)
        except Exception as e:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.critical(
                self,
                "审查失败",
                f"执行审查时发生错误:\n{str(e)}"
            )
