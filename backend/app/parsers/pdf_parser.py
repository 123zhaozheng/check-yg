# -*- coding: utf-8 -*-
"""PDF parser using MinerU document parsing API.

Ports the original ``src/parsers/pdf_parser.py`` behavior into the FastAPI
backend so web extraction can handle heterogeneous PDFs (scanned, multi-column,
encrypted) with the same production assumptions as the desktop pipeline.

Two MinerU modes are supported:

* ``local``  — a self-hosted MinerU endpoint exposing ``/file_parse``.
* ``public`` — the public MinerU agent API (``mineru.net``) with an API key.

Encrypted PDFs are decrypted via :class:`PDFDecryptor` using a password
auto-extracted from the filename, with an optional callback for user input.
"""

import logging
import re
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import pikepdf
import requests

from .base import BaseParser, RawTable
from .html_parser import HTMLTableParser

logger = logging.getLogger(__name__)


class PDFDecryptor:
    """PDF 解密工具类"""

    @staticmethod
    def extract_password_from_filename(filename: str) -> Optional[str]:
        """
        从文件名最后一对括号中提取密码（全角半角均支持）

        例如: "文件名(123456).pdf" -> "123456"
              "文件(注释)(密码).pdf" -> "密码"
        """
        stem = Path(filename).stem
        matches = re.findall(r"[（(](.*?)[）)]", stem)
        if not matches:
            return None
        password = matches[-1].strip()
        return password if password else None

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
        password: str = "",
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
    """Client for a self-hosted MinerU document parsing API."""

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        timeout: int = 300,
        max_retries: int = 3,
        retry_delay: int = 2,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.session = requests.Session()
        # 添加 ngrok 跳过浏览器警告的请求头
        self.session.headers.update(
            {
                "ngrok-skip-browser-warning": "true",
                "User-Agent": "MinerU-Client/1.0",
            }
        )

    def parse_file(self, file_path: Path) -> Dict[str, Any]:
        """Parse a PDF file using the local MinerU API."""
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
                with open(file_path, "rb") as f:
                    files = [("files", (file_path.name, f, "application/pdf"))]
                    response = self.session.post(
                        url,
                        files=files,
                        data=data,
                        timeout=self.timeout,
                    )
                response.raise_for_status()
                return response.json()

            except requests.exceptions.Timeout:
                logger.warning(
                    "Request timeout (attempt %d/%d): %s",
                    attempt + 1,
                    self.max_retries,
                    url,
                )
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)
                else:
                    raise
            except requests.exceptions.RequestException as e:
                logger.warning(
                    "Request failed (attempt %d/%d): %s - %s",
                    attempt + 1,
                    self.max_retries,
                    url,
                    str(e),
                )
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)
                else:
                    raise

        raise requests.exceptions.RequestException("Max retries exceeded")

    def get_markdown(self, file_path: Path) -> str:
        """Parse file and return only markdown content."""
        result = self.parse_file(file_path)
        results = result.get("results", {})
        if not results:
            raise ValueError("No results in response")

        first_result = next(iter(results.values()), {})
        md_content = first_result.get("md_content", "")
        if not md_content:
            raise ValueError("No markdown content in response")
        return md_content

    def health_check(self) -> bool:
        """Check if the API is available."""
        try:
            response = self.session.get(f"{self.base_url}/", timeout=5)
            return response.status_code in (200, 404)
        except Exception:
            return False


class PublicMinerUClient:
    """Client for the MinerU public agent parsing API."""

    def __init__(
        self,
        base_url: str = "https://mineru.net/api/v1/agent",
        api_key: str = "",
        timeout: int = 300,
        max_retries: int = 3,
        retry_delay: int = 2,
        poll_interval: int = 3,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = str(api_key or "").strip()
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.poll_interval = poll_interval
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "MinerU-Public-Client/1.0",
                "Accept": "application/json",
            }
        )
        if self.api_key:
            self.session.headers.update({"Authorization": f"Bearer {self.api_key}"})

    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        last_error: Optional[Exception] = None
        for attempt in range(self.max_retries):
            try:
                response = self.session.request(method, url, timeout=self.timeout, **kwargs)
                response.raise_for_status()
                return response
            except requests.exceptions.RequestException as exc:
                last_error = exc
                logger.warning(
                    "Public MinerU request failed (attempt %d/%d): %s %s - %s",
                    attempt + 1,
                    self.max_retries,
                    method,
                    url,
                    exc,
                )
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)
        if last_error:
            raise last_error
        raise requests.exceptions.RequestException("Max retries exceeded")

    @staticmethod
    def _extract_api_data(result: Dict[str, Any], action: str) -> Dict[str, Any]:
        if result.get("code") != 0:
            raise RuntimeError(result.get("msg") or f"{action}失败")
        data = result.get("data")
        if not isinstance(data, dict):
            raise ValueError(f"{action}返回数据格式错误")
        return data

    def parse_file(self, file_path: Path) -> Dict[str, Any]:
        """Upload a local PDF file to the public MinerU API and wait for completion."""
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        create_resp = self._request(
            "POST",
            f"{self.base_url}/parse/file",
            json={"file_name": file_path.name},
        )
        create_data = self._extract_api_data(create_resp.json(), "创建公网 MinerU 任务")
        task_id = str(create_data.get("task_id") or "").strip()
        file_url = str(create_data.get("file_url") or "").strip()
        if not task_id or not file_url:
            raise ValueError("公网 MinerU 返回缺少 task_id 或 file_url")

        with open(file_path, "rb") as fh:
            upload_resp = self._request(
                "PUT",
                file_url,
                data=fh,
            )
        if upload_resp.status_code not in (200, 201):
            raise RuntimeError(f"公网 MinerU 文件上传失败: HTTP {upload_resp.status_code}")

        deadline = time.time() + self.timeout
        while time.time() < deadline:
            poll_resp = self._request("GET", f"{self.base_url}/parse/{task_id}")
            poll_data = self._extract_api_data(poll_resp.json(), "查询公网 MinerU 任务")
            state = str(poll_data.get("state") or "").strip()
            if state == "done":
                markdown_url = str(poll_data.get("markdown_url") or "").strip()
                if not markdown_url:
                    raise ValueError("公网 MinerU 任务完成，但未返回 markdown_url")
                return {
                    "task_id": task_id,
                    "markdown_url": markdown_url,
                    "state": state,
                }
            if state == "failed":
                err_msg = str(poll_data.get("err_msg") or poll_data.get("msg") or "解析失败")
                raise RuntimeError(f"公网 MinerU 解析失败: {err_msg}")
            time.sleep(self.poll_interval)

        raise requests.exceptions.Timeout(f"公网 MinerU 解析超时: {file_path.name}")

    def get_markdown(self, file_path: Path) -> str:
        """Parse file and return markdown content."""
        result = self.parse_file(file_path)
        markdown_url = result["markdown_url"]
        response = self._request(
            "GET", markdown_url, headers={"Accept": "text/markdown, text/plain"}
        )
        if not response.text:
            raise ValueError("公网 MinerU 未返回 markdown 内容")
        return response.text

    def health_check(self) -> bool:
        """Check if the public API host is reachable."""
        try:
            parsed = urlparse(self.base_url)
            target = (
                f"{parsed.scheme}://{parsed.netloc}"
                if parsed.scheme and parsed.netloc
                else self.base_url
            )
            response = self.session.get(target, timeout=5)
            return response.status_code < 500
        except Exception:
            return False


class PDFParser(BaseParser):
    """PDF parser using the MinerU document parsing API."""

    SUPPORTED_EXTENSIONS = [".pdf"]

    def __init__(
        self,
        mineru_mode: str = "local",
        mineru_url: str = "http://localhost:8000",
        mineru_public_url: str = "https://mineru.net/api/v1/agent",
        mineru_public_api_key: str = "",
        timeout: int = 300,
    ):
        super().__init__()
        self.mineru_mode = (mineru_mode or "local").strip().lower()
        if self.mineru_mode == "public":
            self.client = PublicMinerUClient(
                base_url=mineru_public_url,
                api_key=mineru_public_api_key,
                timeout=timeout,
            )
        else:
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

    def _get_markdown(self, file_path: Path) -> str:
        """Parse PDF with MinerU and return markdown content."""
        if not self.can_parse(file_path):
            raise ValueError(f"Unsupported file type: {file_path.suffix}")

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
                            raise ValueError(error)
                else:
                    # 没有自动密码，直接请求用户输入
                    self.logger.info("No auto password found, requesting user input")
                    temp_file, error = self._request_password_and_decrypt(file_path)

                    if temp_file:
                        actual_path = temp_file
                    elif error:
                        raise ValueError(error)

            # Get markdown content from MinerU
            return self.client.get_markdown(actual_path)

        except requests.exceptions.ConnectionError:
            if self.mineru_mode == "public":
                raise RuntimeError("无法连接到公网 MinerU 服务，请检查网络或接口地址配置")
            raise RuntimeError("无法连接到 MinerU 服务，请检查服务是否启动")
        except Exception as e:
            self.logger.error("Failed to parse PDF %s: %s", file_path.name, e)
            raise
        finally:
            # 清理临时文件
            if temp_file and temp_file.exists():
                try:
                    temp_file.unlink()
                except Exception as e:
                    self.logger.warning("Failed to delete temp file: %s", e)

    def _request_password_and_decrypt(
        self,
        file_path: Path,
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
        """Check if MinerU service is available."""
        return self.client.health_check()

    def extract_raw_tables(self, file_path: Path) -> List[RawTable]:
        """Extract raw HTML tables from MinerU markdown output."""
        try:
            markdown = self._get_markdown(file_path)
        except Exception as exc:
            self.logger.error("Failed to extract raw tables from PDF %s: %s", file_path.name, exc)
            return []
        return self.html_parser.extract_raw_tables_from_html(markdown)

    def extract_non_table_context(self, file_path: Path, max_chars: int = 2000) -> str:
        """
        Extract non-table text content from a PDF for document portrait extraction.

        Removes all HTML table blocks (<table>...</table>) from the MinerU markdown
        output, then truncates the remaining text to max_chars characters.

        Args:
            file_path: Path to the PDF file.
            max_chars: Maximum number of characters to return (default 2000).

        Returns:
            Non-table text content, truncated to max_chars. Empty string on failure.
        """
        try:
            markdown = self._get_markdown(file_path)
        except Exception as exc:
            self.logger.error(
                "Failed to extract non_table_context from PDF %s: %s",
                file_path.name,
                exc,
            )
            return ""

        # Remove all HTML table blocks from the markdown
        non_table_text = re.sub(
            r"<table[^>]*>.*?</table>",
            "",
            markdown,
            flags=re.DOTALL | re.IGNORECASE,
        )

        # Strip excess whitespace
        non_table_text = re.sub(r"\n{3,}", "\n\n", non_table_text).strip()

        # Truncate to max_chars
        if len(non_table_text) > max_chars:
            non_table_text = non_table_text[:max_chars]

        return non_table_text
