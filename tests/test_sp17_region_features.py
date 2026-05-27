"""SP-17 REGION-02: features region_C1/C2/C3 emitidas no hook DNA."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.message_handler import _build_sda_regions


class FakeResult:
    def __init__(self):
        self.score = 4
        self.details = {
            "centers": [30, 14, 4],
            "offset": -3,
            "offset_c3": 6,
            "offset_type": "sigmoid",
        }


class TestRegionBuckets(unittest.TestCase):
    def test_offset_bucket_classification(self):
        regions = _build_sda_regions(FakeResult())
        self.assertEqual(len(regions), 3)
        # C1 offset=0 -> zero
        # C2 offset=-3 -> near (|-3|<=3)
        # C3 offset=6 -> far (>3)
        for r in regions:
            off = r["offset"]
            bucket = "zero" if off == 0 else ("near" if abs(off) <= 3 else "far")
            if r["slot"] == "C1":
                self.assertEqual(bucket, "zero")
            elif r["slot"] == "C2":
                self.assertEqual(bucket, "near")
            elif r["slot"] == "C3":
                self.assertEqual(bucket, "far")


if __name__ == "__main__":
    unittest.main()
