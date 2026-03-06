# -*- coding: utf-8 -*-
"""
Review history persistence manager.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional

from ..config import get_config

if TYPE_CHECKING:
    from .reviewer import ReviewResult

logger = logging.getLogger(__name__)


class ReviewHistoryManager:
    """审查历史持久化管理器。"""

    def __init__(self, review_dir: Optional[Path] = None):
        config = get_config()
        self.review_dir = Path(review_dir) if review_dir else (config.config_dir / "reviews")
        self.review_dir.mkdir(parents=True, exist_ok=True)

    def save_review_result(self, review_result: "ReviewResult", flow_excel_path: str) -> Path:
        """
        保存审查结果到 JSON 文件。

        Args:
            review_result: 审查结果对象。
            flow_excel_path: 流水 Excel 路径。

        Returns:
            保存后的 JSON 路径。
        """
        review_data = review_result.to_dict()
        review_id = str(review_data.get("review_id", "") or "").strip()
        if not review_id:
            review_id = datetime.now().strftime("%Y%m%d_%H%M%S")
            review_data["review_id"] = review_id

        review_data["flow_excel_path"] = flow_excel_path
        review_data["saved_at"] = datetime.now().isoformat()
        save_path = self.review_dir / f"{review_id}.json"
        self._write_json(save_path, review_data)
        logger.info("审查历史已保存: %s", save_path)
        return save_path

    def list_reviews(self) -> List[Dict]:
        """列出所有审查历史摘要。"""
        reviews: List[Dict] = []
        for review_file in self.review_dir.glob("*.json"):
            data = self._read_json(review_file)
            if not data:
                continue
            reviews.append({
                "review_id": data.get("review_id", review_file.stem),
                "review_time": data.get("review_time", ""),
                "saved_at": data.get("saved_at", ""),
                "flow_excel_path": data.get("flow_excel_path", ""),
                "customer_excel_path": data.get("customer_excel_path", ""),
                "total_customers": int(data.get("total_customers", 0) or 0),
                "matched_customers": int(data.get("matched_customers", 0) or 0),
                "total_matches": int(data.get("total_matches", 0) or 0),
                "total_amount": float(data.get("total_amount", 0.0) or 0.0),
            })
        reviews.sort(key=lambda item: item.get("review_time", ""), reverse=True)
        return reviews

    def load_review(self, review_id: str) -> Optional[Dict]:
        """加载单条审查历史详情。"""
        review_path = self.review_dir / f"{review_id}.json"
        if not review_path.exists():
            return None
        return self._read_json(review_path)

    def delete_review(self, review_id: str) -> bool:
        """删除审查历史。"""
        review_path = self.review_dir / f"{review_id}.json"
        if not review_path.exists():
            return False
        try:
            review_path.unlink()
            return True
        except Exception as exc:
            logger.warning("删除审查历史失败 %s: %s", review_id, exc)
            return False

    @staticmethod
    def _read_json(path: Path) -> Optional[Dict]:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            logger.warning("读取审查历史失败 %s: %s", path, exc)
            return None

    @staticmethod
    def _write_json(path: Path, data: Dict) -> None:
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as exc:
            logger.warning("写入审查历史失败 %s: %s", path, exc)
            raise
