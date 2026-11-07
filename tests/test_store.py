"""First-seen tracking for sources that publish no posted date."""
import asyncio
import tempfile
import unittest
from pathlib import Path

from qa_scraper import pipeline
from qa_scraper.models import Board, Job
from qa_scraper.store import Store

DESC = ("Write Playwright and Selenium tests, maintain CI/CD in Jenkins, log defects in Jira, "
        "design test cases for our web application.")


class FakeSource:
    """A board system that, like Manatal/Pinpoint, gives no posted dates."""
    ATS = "fake"

    def __init__(self, titles):
        self.titles = titles

    async def list_jobs(self, http, board):
        return [Job(title=t, company="Acme", job_url=f"https://acme.test/{i}", source="fake",
                    board=board.key, external_id=str(i), description=DESC, remote_type="Remote")
                for i, t in enumerate(self.titles)]


def run_once(store, src):
    board = Board(company="Acme", ats="fake", token="acme")
    pipeline.sources.SOURCES["fake"] = src
    try:
        return asyncio.run(pipeline.run([board], max_age=7, verbose=False, store=store))
    finally:
        pipeline.sources.SOURCES.pop("fake", None)


class TestFirstSeen(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "h.db"

    def tearDown(self):
        self.tmp.cleanup()

    def test_first_scan_of_a_board_never_guesses_a_date(self):
        res = run_once(Store(self.db), FakeSource(["QA Engineer"]))
        self.assertEqual(len(res.kept), 0)
        self.assertEqual(len(res.undated), 1)

    def test_new_job_on_known_board_is_dated_today(self):
        s = Store(self.db)
        s.today = "2026-11-01"
        run_once(s, FakeSource(["QA Engineer"]))             # board first scanned on Nov 1
        s2 = Store(self.db)
        res = run_once(s2, FakeSource(["QA Engineer", "SDET"]))  # today: SDET is new
        kept = {j.title: j for j in res.kept}
        self.assertIn("SDET", kept)
        self.assertEqual(kept["SDET"].date_source, "first_seen")
        self.assertEqual(kept["SDET"].days_old, 0)
        # the old job keeps its first-seen date (Nov 1), not today
        old = [j for j in res.kept + res.undated if j.title == "QA Engineer"]
        self.assertTrue(old)
        self.assertEqual(old[0].posted_date, "2026-11-01")


if __name__ == "__main__":
    unittest.main()
