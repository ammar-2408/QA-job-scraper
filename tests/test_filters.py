"""Run with:  python -m unittest discover tests"""
import unittest

from qa_scraper.filters import enrich, legitimacy, qa_match
from qa_scraper.models import Job

SW_DESC = ("You will write automated tests with Selenium and Playwright, maintain our CI/CD pipeline in "
           "Jenkins, file defects in Jira and design test cases for our web application and mobile app.")
MFG_DESC = ("Ensure GMP compliance on the production line, perform inspection of raw material, maintain "
            "calibration records and support CAPA investigations per ISO 13485 and FDA requirements.")
CALL_DESC = ("Monitor inbound calls at our contact center, score customer interactions and coach agents on "
             "call monitoring results.")

QA_TITLES = [
    "QA Engineer", "Senior QA Automation Engineer", "SDET II", "Software Development Engineer in Test",
    "Software Engineer in Test", "Manual Tester", "Automation Tester", "Software Tester",
    "Test Automation Engineer", "QA Analyst", "Junior QA Tester", "Mobile QA Engineer (iOS/Android)",
    "Game Tester", "Video Game QA Tester", "Playtester", "Localization QA Tester", "Performance Test Engineer",
    "Selenium Automation Engineer", "Playwright Test Engineer", "Cypress Automation Engineer",
    "Appium Mobile Automation Engineer", "QA Lead", "Head of QA", "Director of Quality Engineering",
    "Quality Assurance Engineer - Web Platform", "Software Quality Assurance Engineer", "API Tester",
    "SQA Engineer", "Lead Software Test Engineer", "Principal SDET", "QA Engineer, Growth",
    "Automation QA Engineer - Marketing Platform", "Salesforce QA Analyst", "ETL Tester", "Data QA Engineer",
    "Accessibility Tester", "UAT Tester", "Manual QA Engineer", "JMeter Performance Tester",
    "Test Engineer (Software)", "QA Manual & Automation Engineer", "Sr. QA Engineer - Payments",
]
NOT_QA_TITLES = [
    "Software Engineer", "Senior Backend Engineer", "Product Manager", "Staff Product Manager, Agentic Test Intelligence",
    "Penetration Tester", "Clinical QA Specialist", "Hardware Test Engineer", "Food Safety Quality Manager",
    "Supplier Quality Engineer", "Quality Control Inspector", "Manufacturing Quality Engineer",
    "Drug Testing Technician", "Laboratory Technician", "RF Test Engineer", "Post-Silicon Validation Engineer",
    "Design Verification Engineer", "Growth Experimentation Manager", "A/B Testing Analyst",
    "Account Executive", "Data Scientist", "DevOps Engineer", "Quality Nurse", "Battery Test Engineer",
    "Vehicle Test Driver", "Welding Inspector", "Compliance Analyst", "Sales Manager",
    # Regressions found in the first live audit (2026-11-06):
    "Senior Customer Engineer, Named Enterprise - Montreal, QC", "Growth Marketer (AI-Powered QA Automation)",
    "Staff Product Manager - Agentic Application Security Testing", "Compliance QA Program Manager",
    "Playtest Operations Producer - Global Research Operations", "Binance Accelerator Program - QA (Content)",
    "Manager, EMEA FCC Monitoring & Testing", "Data Quality Engineer",
    "Information Security Engineer (Thick Client Testing / Harness / VAPT)",
    "Team Lead, Quality Analyst, Product Support Operations", "Senior Staff Software Engineer- Search Quality",
    "Credit Model Validation Manager", "Hardware Engineer, Test", "Quality Control Specialist, Sterile (Nights)",
    # Milestone 2 audit:
    "Development Engineer - Refrigeration Testing (f/m/div.)",
    "GCP - Computer System Validation Specialist (12 month limited-term)", "EMC Test Engineer",
    # Milestone 2 full-run audit (Workday brought in chip/hardware and operations roles):
    "ATE Test Engineer", "CPU HVM Functional-Test Verification Engineer", "Data Center Power Test Architect",
    "GPU Validation Engineer", "High-Speed SerDes & Mixed-Signal Validation Engineer", "Senior IC Validation Engineer",
    "Pre-si Power and Performance System Validation Engineer", "SOC Functional Validation Engineer",
    "Senior Product Quality Engineer, Chip - Automotive", "Electrical Test Automation Engineer",
    "Electronics Design Engineer - Test Automation- fixed term", "Product Certification Engineer, Fuel Cell Systems",
    "FW Product Testing Analyst II, Korea", "QA & Authorisation Handler", "Investment Services - QA, AVP",
    "Quality Analyst - Enterprise Transaction Services", "Quality Assurance (QA) Reviewer - AI Data Projects",
    "Creative QA Analyst", "AI for QA Teaching Experts", "Senior Map Data Validation Lead - Autonomous Vehicles",
    "Communications Test Engineer I", "Staff Product Test Engineer", "Digital Validation Engineer",
]
QA_TITLES += [
    "[Internship Program Q1 2027] Automation Test Engineer Intern (Selenium)", "Embedded Software Test Engineer",
    "Senior CUDA Test Development Software Engineer, SDET", "Bulgarian Localization QA Tester / Proofreader",
    "Chapter Area Lead - Software Testing and Test Automation", "GCP QA Automation Engineer",
    "Hardware/Software Testing Intern", "Embedded software test engineer", "Software Verification Engineer - Networking",
    "Platform Software Validation Engineer - SDET", "L6E Software and Technology Validation Engineer",
    "Sr. SW Test Engineer", "Software Test & Verification Engineer (Experienced/Senior)",
    "LQA Game Tester (Japanese) - Freelance Remote", "QA Testers wanted in Jordan!", "Galaxy AI Tester",
]
QA_TITLES += [
    "Senior Engineering Manager, Test Systems & Tooling", "Software Engineer II, Backend (Test Infra)",
    "Software Engineer, Quality", "Senior Software Engineer - Quality", "QA Engineer, Compliance",
    "Middle QA Automation Engineer (AQA)", "Senior Game Tester, Game Modes, Clash Royale",
]


class TestQaMatch(unittest.TestCase):
    def test_qa_titles_are_kept(self):
        missed = [t for t in QA_TITLES if not qa_match.classify(t, SW_DESC)[0]]
        self.assertEqual(missed, [])

    def test_non_qa_titles_are_rejected(self):
        wrong = [t for t in NOT_QA_TITLES if qa_match.classify(t, SW_DESC)[0]]
        self.assertEqual(wrong, [])

    def test_ambiguous_title_needs_software_context(self):
        self.assertTrue(qa_match.classify("Quality Assurance Specialist", SW_DESC)[0])
        self.assertFalse(qa_match.classify("Quality Assurance Specialist", MFG_DESC)[0])
        self.assertFalse(qa_match.classify("Quality Engineer", MFG_DESC)[0])
        self.assertTrue(qa_match.classify("Quality Engineer", SW_DESC)[0])
        self.assertFalse(qa_match.classify("Test Engineer", MFG_DESC)[0])

    def test_strong_title_with_non_software_description(self):
        self.assertFalse(qa_match.classify("QA Specialist", MFG_DESC)[0])
        self.assertFalse(qa_match.classify("QA Analyst", CALL_DESC)[0])

    def test_role_types(self):
        self.assertEqual(qa_match.role_type("SDET"), "Automation / SDET")
        self.assertEqual(qa_match.role_type("Manual Tester"), "Manual QA")
        self.assertEqual(qa_match.role_type("Game Tester"), "Game QA")
        self.assertEqual(qa_match.role_type("QA Manager"), "Management")


class TestEnrich(unittest.TestCase):
    def test_country(self):
        self.assertEqual(enrich.country_from("Lahore, Pakistan"), "Pakistan")
        self.assertEqual(enrich.country_from("Austin, TX"), "United States")
        self.assertEqual(enrich.country_from("Atlanta, Georgia"), "United States")
        self.assertEqual(enrich.country_from("Remote", "GB"), "United Kingdom")
        self.assertEqual(enrich.country_from("Remote"), "")

    def test_salary_needs_pay_context(self):
        self.assertEqual(enrich.salary_from("We raised $50,000,000 in Series B."), "")
        self.assertTrue(enrich.salary_from("The base salary range is $90,000 - $120,000 per year."))

    def test_experience_and_tools(self):
        self.assertEqual(enrich.experience_from("3-5 years of experience in QA"), "3-5 years")
        self.assertEqual(enrich.experience_from("2+ years experience"), "2+ years")
        self.assertIn("Playwright", enrich.tools_from("We use Playwright and Java"))
        self.assertEqual(enrich.tools_from("We use JavaScript").split(", "), ["JavaScript"])


class TestLegitimacy(unittest.TestCase):
    def _job(self, desc, kind="company_ats", **kw):
        return Job(title="QA Tester", company=kw.get("company", "Acme"), job_url="https://x.test/1",
                   source="t", source_kind=kind, description=desc, company_url=kw.get("company_url", ""))

    def test_company_board_is_trusted(self):
        j = self._job(SW_DESC)
        legitimacy.assess(j)
        self.assertEqual(j.trust, "company_ats")

    def test_scam_signals_on_open_job_sites(self):
        for desc in ["Contact us on Telegram to apply and start today.",
                     "You must pay for training equipment before your first shift.",
                     "Send your CV to hiring.acme.jobs@gmail.com to apply.",
                     "Pay a registration fee of $50 to secure your spot."]:
            j = self._job(desc + " " + SW_DESC * 2, kind="aggregator", company_url="https://acme.com")
            legitimacy.assess(j)
            self.assertEqual(j.trust, "flagged", desc)

    def test_strong_scam_signals_on_company_board(self):
        for desc in ["Contact us on Telegram to apply and start today.",
                     "Send your CV to hiring.acme.jobs@gmail.com to apply."]:
            j = self._job(desc + " " + SW_DESC)
            legitimacy.assess(j)
            self.assertEqual(j.trust, "flagged", desc)

    def test_company_board_innocent_phrases_not_flagged(self):
        for desc in ["We pay for your training and ISTQB certification.",
                     "Our app lets customers deposit checks from their phone.",
                     "There is no application fee for our mortgage products."]:
            j = self._job(desc + " " + SW_DESC)
            legitimacy.assess(j)
            self.assertEqual(j.trust, "company_ats", desc)

    def test_aggregator_needs_identity(self):
        j = self._job(SW_DESC * 3, kind="aggregator", company="", company_url="")
        legitimacy.assess(j)
        self.assertEqual(j.trust, "flagged")
        j = self._job("Short QA ad.", kind="aggregator", company_url="https://acme.com")
        legitimacy.assess(j)
        self.assertEqual(j.trust, "flagged")
        # A missing website alone is only a note
        j = self._job(SW_DESC * 3, kind="aggregator", company_url="")
        legitimacy.assess(j)
        self.assertEqual(j.trust, "aggregator_verified")
        self.assertIn("no company website", j.trust_reasons)
        j = self._job(SW_DESC * 3, kind="aggregator", company_url="https://acme.com")
        legitimacy.assess(j)
        self.assertEqual(j.trust, "aggregator_verified")


if __name__ == "__main__":
    unittest.main()
