# -*- coding: utf-8 -*-

import tempfile
import unittest
from pathlib import Path

from src.core.review_history import ReviewHistoryManager
from src.core.reviewer import ReviewMatch, ReviewResult


class ReviewHistoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.review_dir = Path(self._tmpdir.name) / "reviews"
        self.manager = ReviewHistoryManager(review_dir=self.review_dir)

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_save_list_load_delete_review(self) -> None:
        result = ReviewResult(
            review_id="review_001",
            review_time="2026-03-05T10:00:00",
            flow_excel_path="flows.xlsx",
            customer_excel_path="customers.xlsx",
            total_customers=2,
            matched_customers=1,
            total_matches=1,
            total_amount=1000.0,
            matches=[
                ReviewMatch(
                    customer_name="张三",
                    counterparty_name="张三",
                    counterparty_account="62220000",
                    match_type="精确匹配",
                    confidence=100,
                    source_file="flow.xlsx",
                    row_index=2,
                    transaction_time="2026-03-05",
                    amount="1000",
                    summary="转账",
                )
            ],
        )

        save_path = self.manager.save_review_result(result, "C:/data/flows.xlsx")
        self.assertTrue(save_path.exists())

        reviews = self.manager.list_reviews()
        self.assertEqual(1, len(reviews))
        self.assertEqual("review_001", reviews[0].get("review_id"))

        loaded = self.manager.load_review("review_001")
        self.assertIsNotNone(loaded)
        self.assertEqual("review_001", loaded.get("review_id"))
        self.assertEqual("C:/data/flows.xlsx", loaded.get("flow_excel_path"))

        self.assertTrue(self.manager.delete_review("review_001"))
        self.assertFalse(self.manager.delete_review("review_001"))


if __name__ == "__main__":
    unittest.main()
