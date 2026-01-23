# -*- coding: utf-8 -*-
"""
PDF parser using MinerU API
"""

import logging
import re
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

import pikepdf
import requests

from .base import BaseParser, ParseResult, ParsedTable, TableRow
from .html_parser import HTMLTableParser

logger = logging.getLogger(__name__)


class PDFDecryptor:
    """PDF 解密工具类"""
    
    @staticmethod
    def extract_password_from_filename(filename: str) -> Optional[str]:
        """
        从文件名中提取密码（文件名前面的数字）
        例如: "123422大丰xxx.pdf" -> "123422"
        """
        match = re.match(r'^(\d+)', filename)
        if match:
            return match.group(1)
        return None
    
    @staticmethod
    def is_encrypted(file_path: Path) -> bool:
        """检查 PDF 是否加密"""
        try:
            pdf = pikepdf.open(file_path)
            pdf.close()
            return False
        except pikepdf.PasswordError:
            return True
        except Exception:
            return False
    
    @staticmethod
    def decrypt(
        file_path: Path, 
        password: str = ""
    ) -> Tuple[Optional[Path], Optional[str]]:
        """
        解密 PDF 文件
        
        Args:
            file_path: PDF 文件路径
            password: 密码
            
        Returns:
            (解密后的临时文件路径, 错误信息)
            成功时返回 (temp_path, None)
            失败时返回 (None, error_message)
        """
        try:
            logger.info("Attempting to decrypt with password: %s", password)
            pdf = pikepdf.open(file_path, password=password)
            
            # 使用简单的临时文件名避免中文字符问题
            import uuid
            temp_dir = Path(tempfile.gettempdir())
            temp_path = temp_dir / f"decrypted_{uuid.uuid4().hex[:8]}.pdf"
            
            pdf.save(str(temp_path))
            pdf.close()
            
            logger.info("PDF decrypted successfully to: %s", temp_path)
            return temp_path, None
            
        except pikepdf.PasswordError as e:
            logger.error("Password error: %s", e)
            return None, f"密码错误: {e}"
        except Exception as e:
            logger.error("Decrypt error: %s", e)
            return None, str(e)


class MinerUClient:
    """Client for MinerU document parsing API"""
    
    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        timeout: int = 300,
        max_retries: int = 3,
        retry_delay: int = 2,
    ):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.session = requests.Session()
        # 添加 ngrok 跳过浏览器警告的请求头
        self.session.headers.update({
            'ngrok-skip-browser-warning': 'true',
            'User-Agent': 'MinerU-Client/1.0'
        })
    
    def parse_file(self, file_path: Path) -> Dict[str, Any]:
        """Parse a PDF file using MinerU API"""
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        logger.info("Parsing file with MinerU: %s", file_path.name)
        
        data = {
            "return_md": "true",
            "return_content_list": "false",
            "return_images": "false",
        }
        
        url = f"{self.base_url}/file_parse"
        
        for attempt in range(self.max_retries):
            try:
                with open(file_path, 'rb') as f:
                    files = [("files", (file_path.name, f, "application/pdf"))]
                    response = self.session.post(
                        url,
                        files=files,
                        data=data,
                        timeout=self.timeout
                    )
                response.raise_for_status()
                return response.json()
                
            except requests.exceptions.Timeout:
                logger.warning(
                    "Request timeout (attempt %d/%d): %s",
                    attempt + 1, self.max_retries, url
                )
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)
                else:
                    raise
            except requests.exceptions.RequestException as e:
                logger.warning(
                    "Request failed (attempt %d/%d): %s - %s",
                    attempt + 1, self.max_retries, url, str(e)
                )
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)
                else:
                    raise
        
        raise requests.exceptions.RequestException("Max retries exceeded")
    
    def get_markdown(self, file_path: Path) -> str:
        """Parse file and return only markdown content"""
        result = self.parse_file(file_path)
        results = result.get('results', {})
        if not results:
            raise ValueError("No results in response")
        
        first_result = next(iter(results.values()), {})
        md_content = first_result.get('md_content', '')
        if not md_content:
            raise ValueError("No markdown content in response")
        return md_content
    
    def health_check(self) -> bool:
        """Check if the API is available"""
        try:
            response = self.session.get(f"{self.base_url}/", timeout=5)
            return response.status_code in (200, 404)
        except Exception:
            return False


class PDFParser(BaseParser):
    """PDF parser using MinerU API"""
    
    SUPPORTED_EXTENSIONS = ['.pdf']
    
    def __init__(self, mineru_url: str = "http://localhost:8000", timeout: int = 300):
        super().__init__()
        self.client = MinerUClient(base_url=mineru_url, timeout=timeout)
        self.html_parser = HTMLTableParser()
        self.decryptor = PDFDecryptor()
        self._password_callback: Optional[Callable[[str], Optional[str]]] = None
    
    def set_password_callback(self, callback: Callable[[str], Optional[str]]) -> None:
        """
        设置密码回调函数
        
        当 PDF 需要密码且自动提取的密码不正确时，会调用此回调获取用户输入的密码。
        
        Args:
            callback: 回调函数，接收文件名，返回用户输入的密码（取消时返回 None）
        """
        self._password_callback = callback
    
    def parse(self, file_path: Path) -> ParseResult:
        """Parse PDF file using MinerU API"""
        if not self.can_parse(file_path):
            return self._create_error_result(
                file_path, 
                f"Unsupported file type: {file_path.suffix}"
            )
        
        actual_path = file_path
        temp_file: Optional[Path] = None
        
        try:
            # 检查是否加密
            if self.decryptor.is_encrypted(file_path):
                self.logger.info("PDF is encrypted: %s", file_path.name)
                
                # 尝试从文件名提取密码
                auto_password = self.decryptor.extract_password_from_filename(file_path.name)
                
                if auto_password:
                    self.logger.info("Trying auto-extracted password from filename")
                    temp_file, error = self.decryptor.decrypt(file_path, auto_password)
                    
                    if temp_file:
                        actual_path = temp_file
                        self.logger.info("PDF decrypted with auto password")
                    else:
                        # 自动密码失败，尝试回调获取用户输入
                        self.logger.info("Auto password failed, requesting user input")
                        temp_file, error = self._request_password_and_decrypt(file_path)
                        
                        if temp_file:
                            actual_path = temp_file
                        elif error:
                            return self._create_error_result(file_path, error)
                else:
                    # 没有自动密码，直接请求用户输入
                    self.logger.info("No auto password found, requesting user input")
                    temp_file, error = self._request_password_and_decrypt(file_path)
                    
                    if temp_file:
                        actual_path = temp_file
                    elif error:
                        return self._create_error_result(file_path, error)
            
            # Get markdown content from MinerU
            md_content = self.client.get_markdown(actual_path)
            
            # Extract tables from markdown (HTML tables)
            tables = self.html_parser.extract_tables_from_markdown(md_content)
            
            return ParseResult(
                file_path=file_path,  # 返回原始路径
                success=True,
                tables=tables,
                raw_text=md_content,
                metadata={'parser': 'MinerU', 'was_encrypted': temp_file is not None}
            )
            
        except requests.exceptions.ConnectionError:
            return self._create_error_result(
                file_path,
                "无法连接到 MinerU 服务，请检查服务是否启动"
            )
        except Exception as e:
            self.logger.error("Failed to parse PDF %s: %s", file_path.name, e)
            return self._create_error_result(file_path, str(e))
        finally:
            # 清理临时文件
            if temp_file and temp_file.exists():
                try:
                    temp_file.unlink()
                except Exception as e:
                    self.logger.warning("Failed to delete temp file: %s", e)
    
    def _request_password_and_decrypt(
        self, 
        file_path: Path
    ) -> Tuple[Optional[Path], Optional[str]]:
        """
        请求用户输入密码并解密
        
        Returns:
            (解密后的临时文件路径, 错误信息)
        """
        if not self._password_callback:
            return None, f"PDF 文件 {file_path.name} 需要密码，但未设置密码回调"
        
        # 最多尝试 3 次
        for attempt in range(3):
            user_password = self._password_callback(file_path.name)
            
            if user_password is None:
                # 用户取消
                return None, f"用户取消输入密码: {file_path.name}"
            
            temp_file, error = self.decryptor.decrypt(file_path, user_password)
            
            if temp_file:
                return temp_file, None
            
            # 密码错误，继续循环让用户重试
            self.logger.warning("Password attempt %d failed for %s", attempt + 1, file_path.name)
        
        return None, f"密码错误次数过多: {file_path.name}"
    
    def check_service(self) -> bool:
        """Check if MinerU service is available"""
        return self.client.health_check()
