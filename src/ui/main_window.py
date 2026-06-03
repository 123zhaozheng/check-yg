# -*- coding: utf-8 -*-
"""
Main window - application shell with light sidebar navigation
"""

import json
from pathlib import Path

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QPushButton, QLabel, QStackedWidget, QFrame,
    QDialog, QLineEdit, QSpinBox, QMessageBox,
    QComboBox, QGridLayout, QScrollArea,
    QTabWidget
)
from PyQt5.QtCore import Qt

from .styles import MAIN_STYLE, COLORS, SETTINGS_DIALOG_STYLE
from .pages import ResultPage, ExtractPage, ReviewPage, HomePage, ReportPage
from ..config import get_config
from ..core.extraction_result import ExtractionResult
from ..core.reviewer import ReviewMatch, ReviewResult
from ..core.review_history import ReviewHistoryManager
from ..parsers.base import FlowRecord


class SettingsDialog(QDialog):
    """Settings dialog for MinerU and LLM configuration"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.config = get_config()
        self.setWindowTitle("设置")
        self.setMinimumSize(600, 560)
        self.setMaximumSize(700, 800)
        
        # 应用设置对话框样式
        self.setStyleSheet(SETTINGS_DIALOG_STYLE)
        
        self._setup_ui()
        self._load_config()
    
    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(16)
        main_layout.setContentsMargins(20, 20, 20, 20)
        
        # 使用 Tab 页面组织配置
        self.tab_widget = QTabWidget()
        
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
        cancel_btn.setObjectName("settings_cancel_btn")
        cancel_btn.setFixedSize(80, 38)
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        
        save_btn = QPushButton("保存")
        save_btn.setObjectName("settings_save_btn")
        save_btn.setFixedSize(80, 38)
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.clicked.connect(self._save_and_close)
        btn_layout.addWidget(save_btn)
        
        main_layout.addLayout(btn_layout)
    
    def _create_basic_tab(self) -> QWidget:
        """创建基础设置 Tab"""
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # ========== MinerU 区域 ==========
        mineru_title = QLabel("MinerU PDF解析服务")
        mineru_title.setObjectName("settings_title")
        layout.addWidget(mineru_title)

        mineru_mode_label = QLabel("接入方式")
        mineru_mode_label.setObjectName("settings_label")
        layout.addWidget(mineru_mode_label)

        self.mineru_mode_input = QComboBox()
        self.mineru_mode_input.setObjectName("settings_input")
        self.mineru_mode_input.setFixedHeight(40)
        self.mineru_mode_input.addItem("原始服务（本地/自建）", "local")
        self.mineru_mode_input.addItem("公网 Agent 接口", "public")
        layout.addWidget(self.mineru_mode_input)

        mineru_url_label = QLabel("原始服务地址")
        mineru_url_label.setObjectName("settings_label")
        layout.addWidget(mineru_url_label)

        self.mineru_url_input = QLineEdit()
        self.mineru_url_input.setObjectName("settings_input")
        self.mineru_url_input.setPlaceholderText("http://localhost:8000")
        self.mineru_url_input.setFixedHeight(40)
        layout.addWidget(self.mineru_url_input)

        mineru_public_url_label = QLabel("公网接口地址")
        mineru_public_url_label.setObjectName("settings_label")
        layout.addWidget(mineru_public_url_label)

        self.mineru_public_url_input = QLineEdit()
        self.mineru_public_url_input.setObjectName("settings_input")
        self.mineru_public_url_input.setPlaceholderText("https://mineru.net/api/v1/agent")
        self.mineru_public_url_input.setFixedHeight(40)
        layout.addWidget(self.mineru_public_url_input)

        mineru_public_key_label = QLabel("公网接口 Key")
        mineru_public_key_label.setObjectName("settings_label")
        layout.addWidget(mineru_public_key_label)

        self.mineru_public_key_input = QLineEdit()
        self.mineru_public_key_input.setObjectName("settings_input")
        self.mineru_public_key_input.setPlaceholderText("公网接口鉴权 Key")
        self.mineru_public_key_input.setEchoMode(QLineEdit.Password)
        self.mineru_public_key_input.setFixedHeight(40)
        layout.addWidget(self.mineru_public_key_input)
        
        # 分隔线
        layout.addWidget(self._create_separator())
        
        # ========== LLM 基础配置 ==========
        llm_title = QLabel("大模型 API 配置")
        llm_title.setObjectName("settings_title")
        layout.addWidget(llm_title)
        
        # API 地址
        llm_url_label = QLabel("API 地址")
        llm_url_label.setObjectName("settings_label")
        layout.addWidget(llm_url_label)
        
        self.llm_url_input = QLineEdit()
        self.llm_url_input.setObjectName("settings_input")
        self.llm_url_input.setPlaceholderText("https://api.openai.com/v1")
        self.llm_url_input.setFixedHeight(40)
        layout.addWidget(self.llm_url_input)
        
        # 模型名称
        llm_model_label = QLabel("模型名称")
        llm_model_label.setObjectName("settings_label")
        layout.addWidget(llm_model_label)
        
        self.llm_model_input = QLineEdit()
        self.llm_model_input.setObjectName("settings_input")
        self.llm_model_input.setPlaceholderText("gpt-4")
        self.llm_model_input.setFixedHeight(40)
        layout.addWidget(self.llm_model_input)
        
        # API Key
        llm_key_label = QLabel("API Key")
        llm_key_label.setObjectName("settings_label")
        layout.addWidget(llm_key_label)
        
        self.llm_key_input = QLineEdit()
        self.llm_key_input.setObjectName("settings_input")
        self.llm_key_input.setPlaceholderText("sk-...")
        self.llm_key_input.setEchoMode(QLineEdit.Password)
        self.llm_key_input.setFixedHeight(40)
        layout.addWidget(self.llm_key_input)
        
        layout.addStretch()
        return self._wrap_scroll_area(content)
    
    def _create_ai_tab(self) -> QWidget:
        """创建 AI 高级设置 Tab"""
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setSpacing(14)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setAlignment(Qt.AlignTop)
        
        # ========== 流水提取设置 ==========
        extract_title = QLabel("流水提取设置")
        extract_title.setObjectName("settings_title")
        layout.addWidget(extract_title)

        settings_grid = QGridLayout()
        settings_grid.setHorizontalSpacing(24)
        settings_grid.setVerticalSpacing(8)

        flow_batch_label = QLabel("每次给AI行数")
        flow_batch_label.setObjectName("settings_label")
        flow_batch_desc = QLabel("标准化阶段每次发送的行数")
        flow_batch_desc.setObjectName("settings_desc")
        self.flow_batch_spin = QSpinBox()
        self.flow_batch_spin.setObjectName("settings_input")
        self.flow_batch_spin.setRange(1, 100)
        self.flow_batch_spin.setValue(20)
        self.flow_batch_spin.setFixedHeight(40)

        flow_threshold_label = QLabel("表格置信度阈值")
        flow_threshold_label.setObjectName("settings_label")
        flow_threshold_desc = QLabel("高于此值才认定为流水表格")
        flow_threshold_desc.setObjectName("settings_desc")
        self.flow_threshold_spin = QSpinBox()
        self.flow_threshold_spin.setObjectName("settings_input")
        self.flow_threshold_spin.setRange(0, 100)
        self.flow_threshold_spin.setValue(70)
        self.flow_threshold_spin.setSuffix(" 分")
        self.flow_threshold_spin.setFixedHeight(40)

        settings_grid.addWidget(flow_batch_label, 0, 0)
        settings_grid.addWidget(flow_threshold_label, 0, 1)
        settings_grid.addWidget(flow_batch_desc, 1, 0)
        settings_grid.addWidget(flow_threshold_desc, 1, 1)
        settings_grid.addWidget(self.flow_batch_spin, 2, 0)
        settings_grid.addWidget(self.flow_threshold_spin, 2, 1)
        settings_grid.setColumnStretch(0, 1)
        settings_grid.setColumnStretch(1, 1)
        layout.addLayout(settings_grid)
        layout.addStretch()
        
        return self._wrap_scroll_area(content)

    def _wrap_scroll_area(self, content: QWidget) -> QScrollArea:
        """给设置页内容加滚动容器，避免窗口高度不足时控件互相挤压。"""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setWidget(content)
        return scroll
    
    def _create_separator(self) -> QFrame:
        """创建分隔线"""
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFixedHeight(1)
        separator.setStyleSheet(f"background-color: {COLORS['border']}; margin: 8px 0;")
        return separator
    
    def _load_config(self):
        mode = self.config.mineru_mode
        mode_index = self.mineru_mode_input.findData(mode)
        self.mineru_mode_input.setCurrentIndex(mode_index if mode_index >= 0 else 0)
        self.mineru_url_input.setText(self.config.mineru_url)
        self.mineru_public_url_input.setText(self.config.mineru_public_url)
        self.mineru_public_key_input.setText(self.config.mineru_public_api_key)
        self.llm_url_input.setText(self.config.llm_url)
        self.llm_model_input.setText(self.config.llm_model)
        self.llm_key_input.setText(self.config.llm_api_key)
        self.flow_batch_spin.setValue(self.config.flow_batch_size)
        self.flow_threshold_spin.setValue(self.config.flow_confidence_threshold)
    
    def _save_and_close(self):
        self.config.set('mineru.mode', self.mineru_mode_input.currentData() or 'local')
        self.config.set('mineru.url', self.mineru_url_input.text().strip() or 'http://localhost:8000')
        self.config.set(
            'mineru.public_url',
            self.mineru_public_url_input.text().strip() or 'https://mineru.net/api/v1/agent'
        )
        self.config.set('mineru.public_api_key', self.mineru_public_key_input.text().strip())
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
    PAGE_HOME = 0      # 首页
    PAGE_EXTRACT = 1   # 流水提取页
    PAGE_PREVIEW = 2   # 流水预览页
    PAGE_REVIEW = 3    # 审查配置页
    PAGE_RESULT = 4    # 结果展示页
    PAGE_REPORT = 5    # 审查报告页
    
    def __init__(self):
        super().__init__()
        self.config = get_config()
        self.setWindowTitle("员工-客户金额往来审计系统")
        self.setMinimumSize(1100, 700)
        self.resize(1280, 800)
        self.setStyleSheet(MAIN_STYLE)
        self.current_task_id = ""
        self.current_task_title = ""
        self.current_flow_excel_path = ""
        self.current_review_result = None
        self._setup_ui()
        self._connect_signals()
        self._update_navigation_state()
    
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
        self.home_page = HomePage()
        self.extract_page = ExtractPage()
        from .pages.preview_page import PreviewPage
        self.preview_page = PreviewPage()
        self.review_page = ReviewPage()
        self.result_page = ResultPage()
        self.report_page = ReportPage()
        
        # 按顺序添加页面
        self.page_stack.addWidget(self.home_page)      # 索引 0
        self.page_stack.addWidget(self.extract_page)   # 索引 1
        self.page_stack.addWidget(self.preview_page)   # 索引 2
        self.page_stack.addWidget(self.review_page)    # 索引 3
        self.page_stack.addWidget(self.result_page)    # 索引 4
        self.page_stack.addWidget(self.report_page)    # 索引 5
        
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
            ("🏠  首页", "仪表盘与任务历史", self.PAGE_HOME),
            ("📥  流水", "提取银行流水", self.PAGE_EXTRACT),
            ("📋  预览", "查看流水数据", self.PAGE_PREVIEW),
            ("🔍  审查", "匹配客户名单", self.PAGE_REVIEW),
            ("📊  结果", "查看审查结果", self.PAGE_RESULT),
            ("📝  报告", "查看审查报告", self.PAGE_REPORT),
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
        
        version_label = QLabel("v1.1.0")
        version_label.setStyleSheet(f"""
            color: {COLORS['text_light']};
            font-size: 10px;
            padding: 8px;
        """)
        layout.addWidget(version_label)
        
        return sidebar
    
    def _connect_signals(self):
        # HomePage signals
        self.home_page.new_task_requested.connect(self._on_new_task)
        self.home_page.resume_task_requested.connect(self._on_resume_task)
        self.home_page.append_folder_requested.connect(self._on_append_folder)
        
        # ExtractPage -> PreviewPage (flow extraction complete)
        self.extract_page.extraction_completed.connect(self._on_extraction_complete)
        
        # PreviewPage -> ReviewPage (step navigation)
        self.preview_page.configure_review.connect(self._on_configure_review)
        
        # ReviewPage -> PreviewPage (back navigation)
        self.review_page.back_requested.connect(
            lambda: self._switch_page(self.PAGE_PREVIEW)
        )
        
        # ReviewPage -> ResultPage (review complete)
        self.review_page.start_review.connect(self._on_review_start)
        
        # ResultPage -> ExtractPage (new review)
        self.result_page.new_audit_btn.clicked.connect(
            self._on_new_audit_requested
        )
    
    def _switch_page(self, page_index: int) -> None:
        """
        切换到指定页面
        """
        if page_index != self.PAGE_HOME and not self._ensure_task_selected():
            return

        # 刷新首页任务列表（如果是切回首页）
        if page_index == self.PAGE_HOME:
            self.home_page.refresh_tasks()
            
        # 切换页面栈
        self.page_stack.setCurrentIndex(page_index)
        
        # 更新导航按钮状态
        for i, btn in enumerate(self.nav_buttons):
            btn.setChecked(i == page_index)

    def _ensure_task_selected(self) -> bool:
        if self.current_task_id:
            return True
        QMessageBox.information(
            self,
            "请先创建审计任务",
            "当前没有激活的审计任务。\n请先到首页新建或恢复一个审计任务，再进入后续流程。"
        )
        self.page_stack.setCurrentIndex(self.PAGE_HOME)
        for i, btn in enumerate(self.nav_buttons):
            btn.setChecked(i == self.PAGE_HOME)
        return False

    def _update_navigation_state(self) -> None:
        has_task = bool(self.current_task_id)
        for index, btn in enumerate(self.nav_buttons):
            btn.setEnabled(index == self.PAGE_HOME or has_task)

    def _activate_task_context(self, task_id: str, task_title: str = "") -> None:
        self.current_task_id = str(task_id or "").strip()
        self.current_task_title = str(task_title or "").strip()
        self._update_navigation_state()

    def _reset_task_context(self) -> None:
        self.current_task_id = ""
        self.current_task_title = ""
        self.current_flow_excel_path = ""
        self.current_review_result = None
        self.extract_page._task_id = ""
        self.extract_page._task_title = ""
        self.extract_page.task_title_label.setText("当前未绑定审计任务")
        self.result_page.clear()
        self.review_page.clear()
        self.preview_page.clear()
        self.report_page.clear()
        self._update_navigation_state()

    def _on_new_audit_requested(self) -> None:
        self._reset_task_context()
        self._switch_page(self.PAGE_HOME)
    
    def _show_settings(self) -> None:
        """显示设置对话框"""
        dialog = SettingsDialog(self)
        dialog.exec_()

    def _on_new_task(self, task_id: str, task_title: str):
        """处理新建任务"""
        self._activate_task_context(task_id, task_title)
        self._switch_page(self.PAGE_EXTRACT)
        if hasattr(self.extract_page, "set_task_info"):
            self.extract_page.set_task_info(task_title, task_id)

    def _on_resume_task(self, task_id: str):
        """恢复历史任务"""
        task_detail = self.home_page.checkpoint_manager.load_task(task_id) or {}
        task_title = str(task_detail.get("title", "") or "")
        self._activate_task_context(task_id, task_title)
        if hasattr(self.extract_page, "set_task_info"):
            self.extract_page.set_task_info(task_title, task_id)

        if self._restore_review_result(task_id, task_title):
            self._switch_page(self.PAGE_RESULT)
            return

        if self._restore_extraction_preview(task_id):
            self._switch_page(self.PAGE_PREVIEW)
            return

        # 切换到提取页并尝试恢复
        self._switch_page(self.PAGE_EXTRACT)
        if hasattr(self.extract_page, "resume_task"):
            self.extract_page.resume_task(task_id)

    def _on_append_folder(self, task_id: str, folder_path: str):
        """处理追加流水目录请求"""
        task_detail = self.home_page.checkpoint_manager.load_task(task_id) or {}
        task_title = str(task_detail.get("title", "") or "")
        self._activate_task_context(task_id, task_title)
        if hasattr(self.extract_page, "set_task_info"):
            self.extract_page.set_task_info(task_title, task_id)

        # Switch to extract page and start append extraction
        self._switch_page(self.PAGE_EXTRACT)
        if hasattr(self.extract_page, "start_append_extraction"):
            self.extract_page.start_append_extraction(task_id, folder_path)
    
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
    
    def _on_configure_review(self, excel_path: str):
        """处理跳转到审查配置"""
        self.current_flow_excel_path = excel_path
        self.review_page.set_flow_excel_path(excel_path)
        self._switch_page(self.PAGE_REVIEW)
    
    def _on_review_start(self, flow_excel_path: str, customers: list):
        """
        处理审查开始
        执行审查并切换到结果页面
        """
        try:
            from ..core.reviewer import Reviewer
            reviewer = Reviewer()
            result = reviewer.run_review(flow_excel_path, customers=customers)
            self.current_flow_excel_path = flow_excel_path
            self.current_review_result = result
            
            # 传递结果到结果页面
            if hasattr(self.result_page, 'set_review_result'):
                self.result_page.set_review_result(result)
            self.report_page.set_report_result(
                result,
                task_title=self.current_task_title,
                task_id=self.current_task_id,
            )
            
            # 切换到结果页面
            self._switch_page(self.PAGE_RESULT)
            if getattr(result, "writeback_error", ""):
                QMessageBox.warning(
                    self,
                    "写回失败",
                    "已完成匹配，但写回流水Excel失败。\n"
                    "请确认该Excel未被打开后重试。\n\n"
                    f"错误信息: {result.writeback_error}"
                )
        except Exception as e:
            QMessageBox.critical(
                self,
                "审查失败",
                f"执行审查时发生错误:\n{str(e)}"
            )

    def _restore_review_result(self, task_id: str, task_title: str) -> bool:
        review_data = self._find_review_data_for_task(task_id)
        if not review_data:
            return False

        result = self._review_result_from_dict(review_data)
        self.current_flow_excel_path = result.flow_excel_path
        self.current_review_result = result
        self.result_page.set_review_result(result)
        self.report_page.set_report_result(
            result,
            task_title=task_title,
            task_id=task_id,
        )
        return True

    def _restore_extraction_preview(self, task_id: str) -> bool:
        report_path = self.config.reports_folder / f"extract_{task_id}.json"
        if not report_path.exists():
            return False
        try:
            with open(report_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            result = self._extraction_result_from_dict(data)
        except Exception as exc:
            QMessageBox.warning(self, "恢复失败", f"读取提取结果失败:\n{exc}")
            return False

        self.preview_page.set_extraction_result(result)
        return True

    def _find_review_data_for_task(self, task_id: str):
        manager = ReviewHistoryManager(self.config.config_dir / "reviews")
        candidates = []
        for item in manager.list_reviews():
            flow_excel_path = str(item.get("flow_excel_path", "") or "")
            stem = Path(flow_excel_path).stem
            if stem == f"流水_{task_id}" or task_id in flow_excel_path:
                detail = manager.load_review(str(item.get("review_id", "") or ""))
                if detail:
                    candidates.append(detail)
        if not candidates:
            return None
        candidates.sort(
            key=lambda entry: str(entry.get("review_time", "") or entry.get("saved_at", "")),
            reverse=True,
        )
        return candidates[0]

    @staticmethod
    def _review_result_from_dict(data: dict) -> ReviewResult:
        matches = [
            ReviewMatch(
                customer_name=str(item.get("customer_name", "") or ""),
                counterparty_name=str(item.get("counterparty_name", "") or ""),
                counterparty_account=str(item.get("counterparty_account", "") or ""),
                match_type=str(item.get("match_type", "") or ""),
                confidence=int(item.get("confidence", 0) or 0),
                source_file=str(item.get("source_file", "") or ""),
                row_index=int(item.get("row_index", 0) or 0),
                transaction_time=str(item.get("transaction_time", "") or ""),
                amount=str(item.get("amount", "") or ""),
                summary=str(item.get("summary", "") or ""),
            )
            for item in (data.get("matches", []) or [])
        ]
        return ReviewResult(
            review_id=str(data.get("review_id", "") or ""),
            review_time=str(data.get("review_time", "") or ""),
            flow_excel_path=str(data.get("flow_excel_path", "") or ""),
            customer_excel_path=str(data.get("customer_excel_path", "") or ""),
            total_customers=int(data.get("total_customers", 0) or 0),
            matched_customers=int(data.get("matched_customers", 0) or 0),
            total_matches=int(data.get("total_matches", 0) or 0),
            total_amount=float(data.get("total_amount", 0.0) or 0.0),
            matches=matches,
            writeback_error=str(data.get("writeback_error", "") or ""),
        )

    @staticmethod
    def _extraction_result_from_dict(data: dict) -> ExtractionResult:
        records = [
            FlowRecord(
                source_file=str(item.get("source_file", "") or ""),
                original_row=int(item.get("original_row", 0) or 0),
                transaction_time=str(item.get("transaction_time", "") or ""),
                counterparty_name=str(item.get("counterparty_name", "") or ""),
                counterparty_account=str(item.get("counterparty_account", "") or ""),
                amount=str(item.get("amount", "") or ""),
                summary=str(item.get("summary", "") or ""),
                transaction_type=str(item.get("transaction_type", "") or ""),
            )
            for item in (data.get("flow_records", []) or [])
        ]
        return ExtractionResult(
            task_id=str(data.get("task_id", "") or ""),
            task_time=str(data.get("task_time", "") or ""),
            document_folder=str(data.get("document_folder", "") or ""),
            total_documents=int(data.get("total_documents", 0) or 0),
            processed_documents=int(data.get("processed_documents", 0) or 0),
            total_tables=int(data.get("total_tables", 0) or 0),
            flow_tables=int(data.get("flow_tables", 0) or 0),
            total_records=int(data.get("total_records", 0) or 0),
            flow_records=records,
            failed_documents=[str(item) for item in (data.get("failed_documents", []) or [])],
            errors=[
                {str(k): str(v) for k, v in item.items()}
                for item in (data.get("errors", []) or [])
                if isinstance(item, dict)
            ],
        )
