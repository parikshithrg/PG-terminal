import os
import tempfile
import unittest
from pathlib import Path

from summary_cache import EvidenceResponseCache, local_evidence_fingerprint


class EvidenceResponseCacheTest(unittest.TestCase):
    def test_reuses_payload_for_same_evidence_identity(self):
        cache = EvidenceResponseCache()
        calls = []

        def build():
            calls.append(True)
            return {"ok": True, "version": len(calls)}

        first, first_state, _ = cache.get_or_build("dashboard", (1,), build)
        second, second_state, _ = cache.get_or_build("dashboard", (1,), build)

        self.assertEqual(first_state, "miss")
        self.assertEqual(second_state, "hit")
        self.assertIs(first, second)
        self.assertEqual(len(calls), 1)
        self.assertEqual(cache.stats()["hits"], 1)
        self.assertEqual(cache.stats()["misses"], 1)
        self.assertEqual(cache.stats()["hit_rate_pct"], 50.0)

    def test_rebuilds_when_evidence_identity_changes(self):
        cache = EvidenceResponseCache()
        calls = []

        def build():
            calls.append(True)
            return len(calls)

        cache.get_or_build("dashboard", (1,), build)
        payload, state, _ = cache.get_or_build("dashboard", (2,), build)

        self.assertEqual(state, "miss")
        self.assertEqual(payload, 2)

    def test_sqlite_wal_is_part_of_fingerprint(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database = Path(temporary_directory) / "eod.sqlite3"
            database.write_bytes(b"db")
            before = local_evidence_fingerprint(database, business_date="2026-10-28")
            wal = Path(f"{database}-wal")
            wal.write_bytes(b"wal")
            os.utime(wal, None)
            after = local_evidence_fingerprint(database, business_date="2026-10-28")

        self.assertNotEqual(before, after)


if __name__ == "__main__":
    unittest.main()
