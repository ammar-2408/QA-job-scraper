"""Runs table, live saving, NEW and open/closed tracking."""
import asyncio
import tempfile
import unittest
from pathlib import Path

from qa_scraper import pipeline
from qa_scraper.models import Board, Job
from qa_scraper.store import Store
from qa_scraper.text import today

DESC = ("Write Playwright and Selenium tests, maintain CI/CD in Jenkins, log defects in Jira, "
        "design test cases for our web application.")


class DatedSource:
    """A board system with posted dates. `titles=None` simulates an unreachable board."""
    def __init__(self, ats, titles):
        self.ATS, self.titles = ats, titles

    async def list_jobs(self, http, board):
        if self.titles is None:
            return None
        return [Job(title=t, company="Acme", job_url=f"https://acme.test/{board.token}/{t}", source=self.ATS,
                    board=board.key, external_id=t.replace(" ", "-"), description=DESC,
                    posted_date=today().isoformat(), date_source="source", remote_type="Remote")
                for t in self.titles]


class TestLifecycle(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "jobs.db"

    def tearDown(self):
        self.tmp.cleanup()

    def run_once(self, titles, ats="fakeats", token="acme"):
        store = Store(self.path)
        pipeline.sources.SOURCES[ats] = DatedSource(ats, titles)
        try:
            res = asyncio.run(pipeline.run([Board(company="Acme", ats=ats, token=token)], max_age=7,
                                           verbose=False, store=store))
        finally:
            pipeline.sources.SOURCES.pop(ats, None)
        return res, store.run_id

    def jobs(self):
        s = Store(self.path)
        rows = {r["title"]: r for r in s.db.all("SELECT * FROM jobs")}
        s.close()
        return rows

    def run_row(self, run_id):
        s = Store(self.path)
        row = s.db.one("SELECT * FROM runs WHERE id=?", (run_id,))
        s.close()
        return row

    def test_run_row_counts_and_new_jobs(self):
        res, rid = self.run_once(["QA Engineer", "SDET", "Backend Engineer"])
        run = self.run_row(rid)
        self.assertEqual(run["status"], "done")
        self.assertEqual(run["boards_done"], 1)
        self.assertEqual(run["kept"], 2)
        self.assertEqual(run["new_jobs"], 2)
        jobs = self.jobs()
        self.assertEqual(set(jobs), {"QA Engineer", "SDET"})
        self.assertTrue(all(j["first_run_id"] == rid and j["status"] == "open" for j in jobs.values()))

    def test_second_run_new_only_for_new_jobs_and_missing_job_closes(self):
        _, r1 = self.run_once(["QA Engineer", "SDET"])
        res, r2 = self.run_once(["QA Engineer", "Test Automation Engineer"])
        jobs = self.jobs()
        self.assertEqual(jobs["QA Engineer"]["first_run_id"], r1)       # not NEW again
        self.assertEqual(jobs["QA Engineer"]["last_run_id"], r2)
        self.assertEqual(jobs["Test Automation Engineer"]["first_run_id"], r2)
        self.assertEqual(jobs["SDET"]["status"], "closed")
        self.assertEqual(jobs["SDET"]["closed_on"], today().isoformat())
        run = self.run_row(r2)
        self.assertEqual((run["new_jobs"], run["closed_jobs"]), (1, 1))

    def test_failed_board_never_closes_its_jobs(self):
        self.run_once(["QA Engineer"])
        _, r2 = self.run_once(None)                                     # board unreachable
        self.assertEqual(self.jobs()["QA Engineer"]["status"], "open")
        run = self.run_row(r2)
        self.assertEqual(run["boards_failed"], 1)
        self.assertEqual(run["closed_jobs"], 0)

    def test_closed_job_reopens_when_listed_again(self):
        self.run_once(["QA Engineer", "SDET"])
        self.run_once(["QA Engineer"])
        self.assertEqual(self.jobs()["SDET"]["status"], "closed")
        self.run_once(["QA Engineer", "SDET"])
        self.assertEqual(self.jobs()["SDET"]["status"], "open")

    def test_keyword_search_board_not_closed_without_proof(self):
        # Workday finds jobs by keyword search; a missing result alone is not proof the job closed.
        self.run_once(["QA Engineer", "SDET"], ats="workday", token="acme")
        self.run_once(["QA Engineer"], ats="workday", token="acme")
        self.assertEqual(self.jobs()["SDET"]["status"], "open")

    def test_board_status_saved(self):
        self.run_once(["QA Engineer"])
        s = Store(self.path)
        b = s.db.one("SELECT * FROM boards WHERE key='fakeats:acme'")
        s.close()
        self.assertEqual(b["last_status"], "ok")
        self.assertEqual(b["qa_jobs"], 1)
        self.assertEqual(b["last_qa_date"], today().isoformat())


if __name__ == "__main__":
    unittest.main()


class NamedSource(DatedSource):
    """Like DatedSource but the job's company is the board's company."""
    async def list_jobs(self, http, board):
        jobs = await super().list_jobs(http, board)
        for j in jobs or []:
            j.company = board.company
        return jobs


class TestCrossSourceDuplicates(unittest.TestCase):
    setUp, tearDown = TestLifecycle.setUp, TestLifecycle.tearDown

    def test_company_spellings_merged_after_run(self):
        store = Store(self.path)
        pipeline.sources.SOURCES["fakeats"] = NamedSource("fakeats", ["QA Engineer"])
        try:
            asyncio.run(pipeline.run([Board(company="Veeva Systems", ats="fakeats", token="a"),
                                      Board(company="Veeva", ats="fakeats", token="b")],
                                     max_age=7, verbose=False, store=store))
        finally:
            pipeline.sources.SOURCES.pop("fakeats", None)
        s = Store(self.path)
        visible = s.db.all("SELECT * FROM jobs WHERE duplicate=0 AND category='kept'")
        s.close()
        self.assertEqual(len(visible), 1)
