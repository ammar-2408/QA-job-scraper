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
                                          location="Remote", posted_date=today().isoformat(), date_source="source")
                return [mk("QA Engineer", "Remote", 1), mk("SDET", "Hybrid", 2), mk("Test Automation Engineer", "", 3),
                        mk("QA Analyst", "Onsite", 4)]
        pipeline.sources.SOURCES["fakeremote"] = Src()
        try:
            res = asyncio.run(pipeline.run([Board(company="Acme", ats="fakeremote", token="acme")], max_age=7,
                                           verbose=False))
        finally:
            pipeline.sources.SOURCES.pop("fakeremote", None)
        # the unlabelled job's location says "Remote", so it counts as remote
        self.assertEqual([j.title for j in res.kept], ["QA Engineer", "Test Automation Engineer"])
        self.assertEqual(res.counts["not_remote"], 2)


if __name__ == "__main__":
    unittest.main()


class TestLevel(unittest.TestCase):
    def test_senior_titles(self):
        for t in ["Senior QA Engineer", "Sr. SDET", "QA Lead", "Lead Software Test Engineer", "Principal SDET",
                  "Staff QA Automation Engineer", "QA Manager", "Head of QA", "Director of Quality Engineering",
                  "Test Architect", "QA Engineer III", "ANALISTA DE QUALIDADE DE SOFTWARE (QA) SÊNIOR",
                  "Analista de Testes QA Sênior"]:
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


class TestCompanyKey(unittest.TestCase):
    def test_same_company_different_spelling(self):
        from qa_scraper.store import company_key
        for a, b in [("Veeva Systems", "Veeva"), ("CI&T", "ciandt (name unverified)"), ("Qu Pos, Inc.", "Qu"),
                     ("pax8inc (name unverified)", "Pax8"), ("CACI International Inc", "caci (name unverified)")]:
            self.assertEqual(company_key(a), company_key(b), (a, b))
        self.assertNotEqual(company_key("Software Mind"), company_key("Mind"))

    def test_software_qa_still_kept(self):
        from qa_scraper.filters import qa_match
        for t in ["Hybrid QA Engineer", "Salesforce QA Tester DHS Public Trust- Remote", "Tax Software QA & Support Analyst",
                  "Strong Junior Manual QA (Agency team)", "QA Engineer - Game Development (Hard Rock Games)"]:
            self.assertTrue(qa_match.title_candidate(t), t)


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
                  "App Testers wanted in Hawaii, USA!", "Freelance Game LQA Tester Chinese to English",
                  # found in run 14 (2026-11-07)
                  "Casualty Claims QA Internal Auditor", "Default Claims VA QA Analyst, I",
                  "Disability Claims QA Specialist", "QA Examiner/File Review Positions", "Child Welfare QA Analyst",
                  "Commercial QA/QC Specialist", "Cx, QA, & Field, Controls Superintendent",
                  "Editorial QA Specialist and Copy Editor (Spanish)", "Freelance Document Formatting QA Specialist",
                  "Healthcare Intake Specialist /QA Specialist", "Intake QA Coordinator",
                  "Home-Based Product Selection QA Specialist", "Life Contact Center Trainer & QA Analyst",
                  "QA & Training Executive", "Physician Advisory Services QA Specialist",
                  "Arabic Language Expert - QA Specialist", "Sinhala QA Analyst - Fully Remote",
                  "Audio Quality Analyst - AI Trainer", "AI QA Trainer - LLM Evaluation",
                  "AI Data QA & Training Specialist", "AI Agent Tester - Real-World Tasks",
                  "Data & QA Analyst - Impact Investing", "Remote Product Tester & Research Panelist",
                  "Paid Testing Opportunity: California Residents", "Robotics Data Collection Tester",
                  "Relay Testing Professional", "QA/QS Engineer (m/w/d) Data Center", "Connect User Tester",
                  "Design Quality Assurance (DQA) Co-op",
                  # run 17
                  "AI Text Validation Specialist (German language)", "PMO / QA Documental (Remoto LATAM)",
                  "Field Service Technician Coffee/Espresso"]:
            self.assertFalse(qa_match.title_candidate(t), t)


class TestRateLimit(unittest.TestCase):
    def test_long_retry_after_skips_host_for_the_run(self):
        import asyncio
        import httpx
        from qa_scraper.http import Http
        calls = []

        def handler(request):
            calls.append(str(request.url))
            return httpx.Response(429, headers={"Retry-After": "61177"})

        async def go():
            async with Http() as h:
                h.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
                a = await h.get_json("https://apply.workable.com/api/v1/widget/accounts/a")
                b = await h.get_json("https://apply.workable.com/api/v1/widget/accounts/b")
                return a, b, h.blocked
        a, b, blocked = asyncio.run(go())
        self.assertIsNone(a)
        self.assertIsNone(b)
        self.assertEqual(len(calls), 1)
        self.assertIn("apply.workable.com", blocked)


class TestRemoteWording(unittest.TestCase):
    def test_more_remote_statements(self):
        from qa_scraper.models import Job
        for d in ["This opportunity is 100% WFH. You will design test scripts.",
                  "Work Arrangement: Remote  Engagement Type: Contract",
                  "Job Location: Remote work is authorized. Must support US Eastern hours."]:
            self.assertEqual(enrich.remote_from(Job(title="QA Engineer", company="X", job_url="u", source="s",
                                                    location="Atlanta", description=d)), "Remote", d)
        self.assertEqual(enrich.remote_from(Job(title="QA Engineer", company="X", job_url="u", source="s",
                         location="Atlanta", description="Work Arrangement: Hybrid")), "Hybrid")


class TestOpenToHome(unittest.TestCase):
    R = ["Asia", "South Asia", "APAC"]

    def ok(self, country="", location="", desc=""):
        return enrich.open_to(country, location, desc, "Pakistan", self.R)

    def test_worldwide_and_home(self):
        self.assertTrue(self.ok("", "Worldwide"))
        self.assertTrue(self.ok("", "Anywhere"))
        self.assertTrue(self.ok("Pakistan", "Pakistan"))
        self.assertTrue(self.ok("Afghanistan; Pakistan; Bangladesh", ""))
        self.assertTrue(self.ok("", "Remote - APAC"))
        self.assertFalse(self.ok("Philippines", "Anywhere in the Philippines, Philippines"))

    def test_limited_to_other_countries(self):
        self.assertFalse(self.ok("United States", "United States"))    # "United States only"
        self.assertFalse(self.ok("Greece", "Greece"))                  # "Greece only"
        self.assertFalse(self.ok("Canada", "Toronto"))
        self.assertFalse(self.ok("Anguilla; Argentina; Brazil", ""))   # LATAM list
        self.assertFalse(self.ok("", "USA Remote"))
        self.assertFalse(self.ok("", "Zagreb"))

    def test_no_place_named(self):
        self.assertTrue(self.ok("", "Remote", "Join our distributed team. Write Playwright tests."))
        self.assertFalse(self.ok("", "Remote", "You must be authorized to work in the United States."))
        self.assertFalse(self.ok("", "Remote", "This role is US-only."))
        self.assertFalse(self.ok("", "", "Candidates must reside in Canada."))

    def test_limit_in_title(self):
        for t in ["Senior QA Engineer - US Remote", "Senior SDET, Back End [Remote-US]", "LATAM Senior QA Analyst"]:
            self.assertFalse(enrich.open_to("", "Remote", "", "Pakistan", self.R, t), t)
        self.assertTrue(enrich.open_to("", "Remote", "", "Pakistan", self.R, "QA Engineer (Remote)"))
        self.assertTrue(enrich.open_to("", "Remote", "", "Pakistan", self.R, "QA Engineer - US Bank Project"))

    def test_rule_off(self):
        self.assertTrue(enrich.open_to("United States", "", "", "", []))


class TestSeniorWhenOpen(unittest.TestCase):
    def test_senior_kept_only_without_country_limit(self):
        from qa_scraper.store import fails_rules
        base = {"title": "Senior QA Engineer", "remote_type": "Remote", "description": "Playwright tests."}
        self.assertEqual(fails_rules({**base, "country": "", "location": "Worldwide"}), "")
        self.assertEqual(fails_rules({**base, "country": "", "location": "Remote"}), "")
        self.assertEqual(fails_rules({**base, "country": "United States", "location": "United States"}), "too senior")
