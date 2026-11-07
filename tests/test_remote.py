"""Remote-only rules."""
import asyncio
import unittest

from qa_scraper import pipeline
from qa_scraper.filters import enrich
from qa_scraper.models import Board, Job
from qa_scraper.text import today

DESC = ("Write Playwright and Selenium tests, maintain CI/CD in Jenkins, log defects in Jira, "
        "design test cases for our web application.")


def job(**kw):
    base = dict(title="QA Engineer", company="Acme", job_url="https://acme.test/1", source="greenhouse")
    base.update(kw)
    return Job(**base)


class TestRemoteDetection(unittest.TestCase):
    def test_source_label_kept(self):
        self.assertEqual(enrich.remote_from(job(remote_type="Remote", description=DESC)), "Remote")

    def test_remote_label_contradicted_by_text(self):
        j = job(remote_type="Remote", description=DESC + " This is a hybrid role, 3 days per week in the office.")
        self.assertEqual(enrich.remote_from(j), "Hybrid")
        j = job(remote_type="Remote", description=DESC + " This role is on-site in our Austin lab.")
        self.assertEqual(enrich.remote_from(j), "Onsite")

    def test_hybrid_cloud_is_not_hybrid_work(self):
        j = job(remote_type="Remote", description=DESC + " Experience with hybrid cloud platforms.")
        self.assertEqual(enrich.remote_from(j), "Remote")

    def test_location_says_remote(self):
        self.assertEqual(enrich.remote_from(job(location="Remote - Europe")), "Remote")
        self.assertEqual(enrich.remote_from(job(location="Berlin (Hybrid)")), "Hybrid")

    def test_no_statement_is_not_remote(self):
        self.assertEqual(enrich.remote_from(job(location="Austin, TX", description=DESC)), "")


class TestRemoteOnlyPipeline(unittest.TestCase):
    def test_only_remote_jobs_kept(self):
        class Src:
            ATS = "fakeremote"

            async def list_jobs(self, http, board):
                mk = lambda t, rt, i: Job(title=t, company="Acme", job_url=f"https://acme.test/{i}", source="fakeremote",
                                          board=board.key, external_id=str(i), description=DESC, remote_type=rt,
                                          location="Austin, TX", posted_date=today().isoformat(), date_source="source")
                return [mk("QA Engineer", "Remote", 1), mk("SDET", "Hybrid", 2), mk("Test Automation Engineer", "", 3),
                        mk("QA Analyst", "Onsite", 4)]
        pipeline.sources.SOURCES["fakeremote"] = Src()
        try:
            res = asyncio.run(pipeline.run([Board(company="Acme", ats="fakeremote", token="acme")], max_age=7,
                                           verbose=False))
        finally:
            pipeline.sources.SOURCES.pop("fakeremote", None)
        self.assertEqual([j.title for j in res.kept], ["QA Engineer"])
        self.assertEqual(res.counts["not_remote"], 3)


if __name__ == "__main__":
    unittest.main()


class TestLevel(unittest.TestCase):
    def test_senior_titles(self):
        for t in ["Senior QA Engineer", "Sr. SDET", "QA Lead", "Lead Software Test Engineer", "Principal SDET",
                  "Staff QA Automation Engineer", "QA Manager", "Head of QA", "Director of Quality Engineering",
                  "Test Architect", "QA Engineer III"]:
            self.assertTrue(enrich.too_senior_title(t), t)
        for t in ["QA Engineer", "Junior QA Tester", "QA Intern", "Mid-level QA Automation Engineer", "SDET II",
                  "Software Tester", "Manual QA Engineer"]:
            self.assertFalse(enrich.too_senior_title(t), t)

    def test_experience_limit(self):
        self.assertEqual(enrich.min_years(enrich.experience_from("3+ years of experience in QA")), 3)
        self.assertEqual(enrich.min_years(enrich.experience_from("5-8 years of QA experience")), 5)
        self.assertEqual(enrich.min_years(enrich.experience_from("7+ years of software testing experience")), 7)
        self.assertIsNone(enrich.min_years(enrich.experience_from("We value curiosity.")))


class TestExperienceParsing(unittest.TestCase):
    def test_half_year_is_not_five(self):
        self.assertEqual(enrich.min_years(enrich.experience_from("0.5+ years of relevant experience as a QA")), None)

    def test_company_age_ignored(self):
        self.assertEqual(enrich.experience_from("with 30+ years of experience in localization, we..."), "")

    def test_tool_title_is_a_tester(self):
        from qa_scraper.filters import qa_match
        self.assertTrue(qa_match.title_candidate("iOS Engineer / XCUITest Automation"))


class TestCountryAndScope(unittest.TestCase):
    def test_india_only_jobs_excluded(self):
        self.assertTrue(enrich.excluded_country("India", "", ["India"]))
        self.assertTrue(enrich.excluded_country("Bangladesh; India", "", ["India"]))
        self.assertTrue(enrich.excluded_country("", "Bengaluru, India (Remote)", ["India"]))
        self.assertFalse(enrich.excluded_country("Poland; Portugal", "", ["India"]))
        self.assertFalse(enrich.excluded_country("Afghanistan; Albania; India; Pakistan; Spain", "", ["India"]))

    def test_not_software_qa(self):
        from qa_scraper.filters import qa_match
        for t in ["User Experience Study Tester - OKX Crypto Exchange", "Usability Tester", "Risk (QA) Engineer",
                  "App Testers wanted in Hawaii, USA!", "Freelance Game LQA Tester Chinese to English"]:
            self.assertFalse(qa_match.title_candidate(t), t)
