# -*- coding: utf-8 -*-
"""
员工-客户金额往来审计系统
主入口文件
"""

import sys
import os
import logging
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

from src.ui import MainWindow
from src.config import get_config


def setup_logging():
    """Setup application logging"""
    from datetime import datetime
    
    # 日志目录：~/.check-yg/logs/
    config = get_config()
    log_dir = config.config_dir / 'logs'
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # 日志文件名：audit_YYYYMMDD.log
    log_file = log_dir / f"audit_{datetime.now().strftime('%Y%m%d')}.log"
    
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    # 配置根日志器
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        handlers=[
            logging.StreamHandler(),  # 控制台输出（开发时可见）
            logging.FileHandler(log_file, encoding='utf-8'),  # 文件输出
        ]
    )
    
    logging.info(f"日志文件: {log_file}")


def setup_high_dpi():
    """Enable high DPI scaling for better display on modern screens"""
    if hasattr(Qt, 'AA_EnableHighDpiScaling'):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)


def ensure_directories():
    """Ensure required directories exist"""
    config = get_config()
    
    dirs = [
        config.config_dir,
        config.input_folder,
        config.output_folder,
        config.reports_folder,
    ]
    
    for dir_path in dirs:
        Path(dir_path).mkdir(parents=True, exist_ok=True)


def main():
    """Application entry point"""
    # Setup
    setup_logging()
    setup_high_dpi()
    ensure_directories()
    
    # Create application
    app = QApplication(sys.argv)
    app.setApplicationName("员工-客户金额往来审计系统")
    app.setApplicationVersion("1.0.0")
    
    # Set default font
    font = QFont("Microsoft YaHei", 10)
    app.setFont(font)
    
    # Create and show main window
    window = MainWindow()
    window.show()
    
    # Run event loop
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
