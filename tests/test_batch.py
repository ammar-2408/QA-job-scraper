"""Website runs: one run split into many short steps."""
import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from qa_scraper import batch, pipeline
from qa_scraper.db import DB
from qa_scraper.models import Board
from tests.test_lifecycle import DatedSource


class TestBatch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = DB(f"sqlite:///{Path(self.tmp.name) / 'jobs.db'}")
        self.db.init_schema()
        self.boards = [Board(company=f"Co{i}", ats="fakeats", token=f"co{i}") for i in range(7)]
        self.titles = {b.token: ["QA Engineer", "SDET", "Backend Engineer"] for b in self.boards}

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def items(self, db, mode, created_at=None, run_id=None):
        return [("board", b) for b in self.boards]

    def full_run(self, step_size=2):
        src = DatedSource("fakeats", None)

        async def list_jobs(http, board):
            src.titles = self.titles[board.token]
            jobs = await DatedSource.list_jobs(src, http, board)
            for j in jobs:
                j.company = board.company
            return jobs
        src.list_jobs = list_jobs
        pipeline.sources.SOURCES["fakeats"] = src
        try:
            with mock.patch.object(batch, "run_items", self.items), mock.patch.object(batch, "FIRST_STEP", step_size), \
                    mock.patch.object(batch, "MAX_STEP", step_size), mock.patch.object(batch, "MIN_STEP", 1):
                rid = batch.create_run(self.db, "full", 7)
                steps = 0
                while True:
                    run = asyncio.run(batch.step(self.db, rid, budget=30))
                    steps += 1
                    if run["status"] not in batch.ACTIVE or steps > 50:
                        break
        finally:
            pipeline.sources.SOURCES.pop("fakeats", None)
        return run, steps

    def test_run_in_slices_covers_every_board_once(self):
        run, steps = self.full_run(step_size=2)
        self.assertEqual(run["status"], "done")
        self.assertGreater(steps, 2)
        self.assertEqual(run["boards_done"], 7)
        self.assertEqual(run["kept"], 14)            # 7 boards x (QA Engineer, SDET)
        self.assertEqual(run["new_jobs"], 14)

    def test_second_sliced_run_closes_missing_jobs(self):
        self.full_run()
        self.titles["co3"] = ["QA Engineer"]          # SDET at co3 was taken down
        run, _ = self.full_run(step_size=3)
        self.assertEqual((run["new_jobs"], run["closed_jobs"]), (0, 1))

    def test_cancel(self):
        with mock.patch.object(batch, "run_items", self.items):
            rid = batch.create_run(self.db, "full", 7)
            asyncio.run(batch.cancel(self.db, rid))
        self.assertEqual(self.db.one("SELECT status FROM runs WHERE id=?", (rid,))["status"], "cancelled")


if __name__ == "__main__":
    unittest.main()
