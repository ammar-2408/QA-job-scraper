"""Is this a software QA / testing job?  Rule-based, no AI.

Three tiers of title evidence:

  STRONG  - unambiguous software-testing titles: QA Engineer, SDET, Software Tester,
            Manual/Automation Tester, Test Automation, "Engineer in Test", titles that
            name a testing tool (Selenium, Playwright, Cypress, Appium, ...).
            Kept unless the description is clearly manufacturing/pharma/lab work.
  MEDIUM  - titles used in software AND non-software fields: Quality Assurance,
            Quality Engineer, Test Engineer, Tester, Validation, UAT.
            Kept only when the title or description shows software context.
  EXCLUDE - titles that are never software QA (pen-testing, drug testing, food
            safety, hardware/silicon test, quality inspectors, A/B experiments...).

Only the TITLE decides whether a job is a candidate - a developer posting that says
"write unit tests" in its description is NOT a QA job.
"""
from __future__ import annotations

import re

_I = re.IGNORECASE


def _rx(*parts: str) -> re.Pattern:
    return re.compile("|".join(parts), _I)


# ── Title: strong QA signals ────────────────────────────────────────────────
STRONG = _rx(
    r"\bQA\b", r"\bQ\.A\.", r"\bSQA\b", r"\bQAE\b",
    r"\bSDETs?\b", r"(?-i:\bSETs?\b)(?=.*\b(engineer|test)\b)", r"(?-i:\bSTE\b)",
    r"\b(software|mobile|web|app|game|games|api|automation|automated|manual|functional|regression|"
    r"performance|load|stress|accessibility|localization|localisation|lqa|usability|ui|ux|"
    r"integration|e2e|end[- ]to[- ]end|qa|crowd|beta|play|video ?game|console|embedded software|"
    r"salesforce|sap|erp|etl|data|bi|database|db|backend|front[- ]?end|frontend|cloud|devops|"
    r"ios|android|blockchain|smart contract|ai|ml|llm|chatbot|test)\s*"
    r"(tester|testers|testing engineer|test engineer|test analyst|test lead|test manager|"
    r"test architect|test specialist|test consultant|test developer|test automation|qa)\b",
    r"\btest(ing)? automation\b", r"\bautomation (test|testing|qa)\b", r"\bautomat(ed|ion) tester\b",
    r"\b(software|sw) (test|testing|quality|verification)\b",
    r"\b(engineer|developer|analyst)s? in test\b", r"\bsoftware engineer,? test\b",
    r"\bquality assurance (engineer|analyst|tester|automation|lead|manager|architect|specialist)\b"
    r"(?=.*\b(software|web|mobile|app|digital|it|technology|platform|product|automation|game)\b)",
    r"\bplaytest(er|ing)?\b", r"\bgame (tester|testing|qa)\b",
    r"\b(manual|automation|automated|functional|regression|mobile|api|web|performance|load)\s+qa\b",
    r"\btest(ing)? (engineer|analyst|lead|manager|architect|specialist|consultant|coordinator|developer)\b"
    r"(?=.*\b(software|web|mobile|app|api|automation|qa|digital|game|it|cloud|saas)\b)",
    r"\b(selenium|playwright|cypress|appium|webdriver ?io|wdio|testng|cucumber|katalon|"
    r"robot framework|jmeter|gatling|loadrunner|k6|rest ?assured|postman|tosca|testcomplete|"
    r"ranorex|uft|qtp|xcuitest|espresso|detox|browserstack|pytest|test ?cafe|testim|mabl)\b",
    r"\bquality engineer(ing)?\b(?=.*\b(software|qa|automation|test|web|mobile|platform|frontend|backend)\b)",
    r"\b(head|director|vp|chief) of (qa|quality assurance|quality engineering|testing|test)\b",
    r"\bqa/qc\b(?=.*\b(software|web|mobile|app)\b)",
)

# ── Title: ambiguous signals (need software context) ────────────────────────
MEDIUM = _rx(
    r"\bquality assurance\b", r"\bquality engineer(ing)?\b", r"\bquality analyst\b",
    r"\btest(ing)? (engineer|analyst|lead|manager|architect|specialist|consultant|coordinator|developer)\b",
    r"\btesters?\b", r"\btesting\b", r"\bvalidation (engineer|analyst|specialist|lead)\b",
    r"\bverification (engineer|analyst)\b", r"\bUAT\b", r"\buser acceptance\b",
    # (no bare "QC": in titles it is as often Quebec as quality control)
    r"\bquality (lead|manager|specialist|coordinator)\b", r"(?-i:\bQE\b)",
    r"\bcertification (engineer|analyst|tester)\b", r"\breliability engineer\b(?=.*\btest)",
)

# ── Title: never software QA ─────────────────────────────────────────────────
# HARD: other industries entirely. Applies even to strong titles ("Clinical QA
# Specialist", "Hardware Test Engineer") unless the title itself says software.
HARD_EXCLUDE = _rx(
    r"\bpen(etration)?[- ]?test", r"\bred team", r"\bethical hack", r"\bsecurity tester\b",
    r"\bdrug\b", r"\bclinical\b", r"\blab(oratory)?\b", r"\bpatholog", r"\bphlebotom", r"\bspecimen",
    r"\bfood\b", r"\bhaccp\b", r"\bgmp\b", r"\bpharma", r"\bbiolog", r"\bchemist", r"\bmicrobio",
    r"\bmedical device", r"\bweld", r"\bndt\b", r"\bnon[- ]?destructive\b",
    r"\bconstruction\b", r"\bcivil\b", r"\bconcrete\b", r"\bgeotech",
    r"\bsupplier quality\b", r"\bsupply chain quality\b", r"\bmanufacturing\b", r"\bproduction (quality|test)\b",
    r"\binspector\b", r"\binspection\b", r"\bcalibration\b",
    r"\bvehicle test", r"\btest driver\b", r"\bdrive test", r"\bflight test", r"\bcrash test",
    r"\bwind tunnel", r"\bpowertrain", r"\bavionics", r"\bdyno",
    r"\bnurs(e|ing)\b", r"\bquality of care\b", r"\bhealthcare quality\b",
    # Operations / service "QA" (reviewing claims, transactions, AI training data, ad creatives...)
    r"\bauthori[sz]ation\b", r"\binvestment services\b", r"\btransaction services\b", r"\breviewer\b",
    r"\bcreative\b", r"\bteaching\b", r"\binstructor\b", r"\bfield quality\b", r"\bfootwear\b",
    r"(?-i:\bFW\b)", r"\bapparel\b", r"\bmap data\b", r"\bfuel cell", r"\bcertification engineer\b",
    # Non-software "QA/testing" functions inside tech companies.
    r"\bcompliance\b", r"\baml\b", r"\bkyc\b", r"\bfcc\b", r"\bcontrols? testing\b", r"\bmodel validation\b",
    r"\bmonitoring (&|and) testing\b", r"\bcontent\b", r"\bsupport operations\b", r"\bcustomer support\b",
    r"\bdata quality\b", r"\bunderwriting\b", r"\bmerchant risk\b", r"\bvapt\b", r"\bsecurity testing\b",
    # Physical-product testing at industrial employers (Bosch, Siemens, automotive...)
    r"\brefrigerat", r"\bhvac\b", r"\bappliance", r"\bhydraulic", r"\bpneumatic", r"\bcombustion\b",
    r"\bengine (test|testing|calibration)\b", r"\bbrake", r"\bchassis\b", r"\bstructural\b", r"\bmaterials? test",
    r"\benvironmental test", r"\bemc\b", r"\bemi\b", r"\bacoustic", r"\bvibration", r"\bdurability\b",
    r"\bfluid", r"\bpackaging\b", r"\btextile", r"\bsoil\b", r"\bpipeline integrity\b",
    # Pharma / life-science computer-system validation (regulated GxP work, not software QA)
    r"\bcomputer systems? validation\b", r"\bgxp\b", r"(?-i:\bCSV\b)", r"\bgcp\s*[-\u2013:]",
)
# HARDWARE: chip / electronics / physical-device testing and validation. Only an
# explicit "software" in the title overrides this - "Electrical Test Automation
# Engineer" and "GPU Validation Engineer" are hardware jobs even though they say
# "test automation" / "validation".
HARDWARE_EXCLUDE = _rx(
    r"\bhardware\b", r"\bsilicon\b", r"\bpre[- ]?si\b", r"\bpost[- ]?si\b", r"\basic\b", r"\bfpga\b",
    r"\bsoc\b", r"\bdft\b", r"\brf\b", r"\bantenna", r"\bbattery\b", r"\bcell test", r"\bmechanical\b",
    r"\belectrical\b", r"\belectronics?\b", r"\bpcb\b", r"\bsemiconductor", r"\bwafer", r"\boptical\b",
    r"\bphotonic", r"\bthermal\b", r"\bdesign verification\b", r"\bserdes\b", r"\bmixed[- ]signal\b",
    r"\banalog\b", r"\bic\b", r"\bcpu\b", r"\bgpu\b", r"\bchip\b", r"\bboard\b", r"\bate\b", r"\bhvm\b",
    r"\bpower (test|validation|architect)", r"\bproduct quality engineer\b", r"\bproduct test engineer\b",
    r"\bcommunications test\b", r"\bdigital validation\b", r"\bplatform validation\b", r"\bic validation\b",
    r"\bvalidation engineer\b(?!.*\bsoftware\b)",
)
_HARDWARE_OVERRIDE = re.compile(r"\b(software|sw)\b", _I)

# ROLE: the job itself is a different profession, even if it mentions QA/testing
# ("Growth Marketer (AI-Powered QA Automation)", "Product Manager - Security Testing").
# No override.
ROLE_EXCLUDE = _rx(
    r"\bmarketer\b", r"\bmarketing manager\b", r"\bproduct manager\b", r"\bproducer\b",
    r"\brecruit(er|ing)\b", r"\btalent acquisition\b", r"\bsales\b", r"\baccount (executive|manager)\b",
    r"\bcustomer engineer\b", r"\bsolutions? engineer\b", r"\bsecurity (engineer|analyst)\b",
    r"\bcopywriter\b", r"\bdesigner\b", r"\bdata scientist\b", r"\bresearch scientist\b",
)
# DEVELOPER: building software is a different job from testing it. Dropped unless the
# title itself says the job is testing ("Software Engineer in Test", "QA Engineer").
DEV_EXCLUDE = _rx(
    r"\bdevelopers?\b", r"\bprogrammer\b", r"\bsoftware engineer(ing)?\b", r"\bfull[- ]?stack\b",
    r"\bback[- ]?end\b", r"\bfront[- ]?end\b", r"\bdevops\b", r"\bsite reliability\b", r"(?-i:\bSRE\b)",
    r"\bdata engineer", r"\b(machine learning|ml|ai) engineer", r"\bplatform engineer", r"\binfrastructure\b",
    r"\bfirmware\b", r"\bembedded engineer", r"\b(ios|android|mobile) engineer", r"\btooling\b",
    r"\btest (systems|infra|frameworks?|tools|platform)\b", r"\breliability engineer\b",
)
_TESTER_OVERRIDE = re.compile(
    r"\b(testers?|test engineer|test analyst|qa engineer|qa analyst|qa tester|qa automation|sdets?|in test|"
    r"test automation|automation test(er|ing)?|quality assurance (engineer|analyst|tester)|"
    r"selenium|playwright|cypress|appium|xcuitest|espresso|webdriver ?io|detox|katalon)\b", _I)
# LANGUAGE: linguistic review / proofreading jobs (they check wording, not software behaviour).
LANGUAGE_EXCLUDE = _rx(r"\bproofread", r"\blinguist", r"\btranslat", r"\bsubtitl", r"\blanguage specialist\b",
                       r"\blqa\b", r"\blocali[sz]ation", r"\b(chinese|japanese|korean|spanish|french|german|italian|"
                       r"portuguese|russian|turkish|polish|arabic|ukrainian|dutch|thai|vietnamese) (to|tester|qa)\b")
# NOT QA: user-research participants, crowd-testing gig ads, risk / fraud "QA".
OTHER_EXCLUDE = _rx(r"\b(user experience|ux|usability) (study )?tester\b", r"\bstudy tester\b",
                    r"\btesters? wanted\b", r"\brisk\b", r"\bfraud\b", r"\bcommunity\b$")

# SOFT: non-QA job families. Only applies to ambiguous (medium) titles, so a real
# "QA Engineer - Growth" or "SDET, Marketing Platform" is still kept.
SOFT_EXCLUDE = _rx(
    r"\ba/b\b", r"\bexperimentation\b", r"\bconversion rate", r"(?-i:\bCRO\b)",
    r"\bcall quality\b", r"\bcustomer (service|support) quality\b", r"\bpatient\b",
    r"\bclaims\b", r"\bunderwrit", r"\bmortgage\b", r"\bloan\b", r"\bcredit (risk|quality)\b",
    r"\bdata quality steward\b", r"\baudit(or)?\b", r"\bcompliance\b", r"\bregulatory\b",
    r"\bsafety\b", r"\bhse\b", r"\behs\b", r"\bcontent (quality|moderat)", r"\bannotat",
    r"\bdata label", r"\brater\b", r"\bsearch quality\b", r"\bteacher\b", r"\btutor\b",
    r"\bexam\b", r"\bassessment\b", r"\bpsychometric", r"\bsales\b", r"\baccount executive\b",
    r"\brecruit", r"\bmarketing\b", r"\bgrowth\b",
)
_SOFTWARE_OVERRIDE = re.compile(
    r"\b(software|sdet|qa automation|test automation|qa engineer|engineer in test|automation engineer)\b", _I)

# Words in the title that place an ambiguous title in software.
TITLE_SOFTWARE = _rx(
    r"\b(software|sw|web|mobile|app|apps|application|digital|it|technology|tech|platform|product|"
    r"automation|automated|game|games|gaming|api|saas|cloud|devops|frontend|front[- ]end|backend|"
    r"back[- ]end|ios|android|salesforce|sap|erp|crm|etl|data|bi|ai|ml|e-?commerce|fintech|"
    r"manual|functional|regression|ui|ux|selenium|cypress|playwright|appium)\b",
)

# Description evidence.
DESC_SOFTWARE = [
    r"selenium", r"playwright", r"cypress", r"appium", r"webdriver", r"testng", r"junit", r"pytest",
    r"\bjest\b", r"mocha", r"cucumber", r"gherkin", r"\bbdd\b", r"postman", r"rest[- ]?assured",
    r"soap ?ui", r"jmeter", r"gatling", r"\bk6\b", r"locust", r"loadrunner", r"testrail", r"zephyr",
    r"\bxray\b", r"qtest", r"\bjira\b", r"ci/cd", r"jenkins", r"github actions", r"gitlab ci",
    r"regression test", r"test cases?\b", r"test plans?\b", r"test scripts?\b", r"test suites?\b",
    r"bug (report|track)", r"\bdefects?\b", r"api testing", r"automation framework", r"\bsdlc\b",
    r"\bstlc\b", r"\bagile\b", r"\bscrum\b", r"web applications?", r"mobile app", r"\bios\b",
    r"\bandroid\b", r"katalon", r"robot framework", r"browserstack", r"sauce ?labs", r"xcuitest",
    r"espresso", r"\bdetox\b", r"end[- ]to[- ]end", r"\be2e\b", r"smoke test", r"exploratory testing",
    r"functional testing", r"black[- ]box", r"white[- ]box", r"\bsql\b", r"\bjavascript\b",
    r"typescript", r"\bpython\b", r"\bjava\b", r"\bc#\b", r"software", r"\bsaas\b", r"microservices",
    r"\bistqb\b", r"test automation", r"user acceptance testing", r"\buat\b",
]
DESC_NON_SOFTWARE = [
    r"\bgmp\b", r"\bfda\b", r"iso ?13485", r"iso ?9001", r"\bcapa\b", r"\bhaccp\b", r"manufactur",
    r"production line", r"\bsupplier", r"inspection", r"calibrat", r"laborator", r"clinical",
    r"pharmaceutical", r"batch record", r"food safety", r"welding", r"as9100", r"iatf", r"\bppap\b",
    r"\bapqp\b", r"assembly line", r"raw material", r"warehouse", r"forklift", r"sterile",
    r"medical device", r"\bglp\b", r"\bgcp\b", r"\bcmm\b", r"blueprints?", r"tolerances?",
    r"call cent(er|re)", r"contact cent(er|re)", r"inbound calls", r"customer interactions",
    r"call monitoring", r"loan files?", r"underwriting", r"mortgage", r"medical records",
    r"chart review", r"claims processing", r"patient care", r"coach(ing)? agents",
    # chip / electronics design and lab work
    r"\brtl\b", r"verilog", r"systemverilog", r"\buvm\b", r"oscilloscope", r"schematic", r"post[- ]silicon",
    r"pre[- ]silicon", r"bring[- ]up", r"\bwafer", r"mixed[- ]signal", r"\bserdes\b", r"\bpcb\b",
    r"solder", r"characteri[sz]ation", r"\bate\b", r"spectrum analy[sz]er", r"signal integrity",
]
_DESC_SW = [re.compile(p, _I) for p in DESC_SOFTWARE]
_DESC_NSW = [re.compile(p, _I) for p in DESC_NON_SOFTWARE]


def _count(patterns, text: str) -> int:
    return sum(1 for p in patterns if p.search(text))


def title_candidate(title: str) -> str:
    """Cheap title-only check used BEFORE fetching descriptions.
    Returns 'strong', 'medium' or '' (not a candidate)."""
    t = title or ""
    if ROLE_EXCLUDE.search(t) or LANGUAGE_EXCLUDE.search(t) or OTHER_EXCLUDE.search(t):
        return ""
    if DEV_EXCLUDE.search(t) and not _TESTER_OVERRIDE.search(t):
        return ""
    if HARD_EXCLUDE.search(t) and not _SOFTWARE_OVERRIDE.search(t):
        return ""
    if HARDWARE_EXCLUDE.search(t) and not _HARDWARE_OVERRIDE.search(t):
        return ""
    if STRONG.search(t):
        return "strong"
    if MEDIUM.search(t) and not SOFT_EXCLUDE.search(t):
        return "medium"
    return ""


def _non_software(sw: int, nsw: int) -> bool:
    return (nsw >= 3 and sw <= 1) or (nsw >= 2 and sw == 0)


def classify(title: str, description: str = "") -> tuple[bool, str]:
    """Final decision once the description is known. Returns (is_qa, reason)."""
    tier = title_candidate(title)
    if not tier:
        return False, ""
    desc = description or ""
    sw, nsw = _count(_DESC_SW, desc), _count(_DESC_NSW, desc)
    if tier == "strong":
        if _non_software(sw, nsw):
            return False, f"title looks QA but description is non-software (sw={sw}, non-sw={nsw})"
        return True, "strong title"
    # medium: needs software context from the title or the description
    if TITLE_SOFTWARE.search(title):
        if _non_software(sw, nsw):
            return False, f"ambiguous title, non-software description (sw={sw}, non-sw={nsw})"
        return True, "ambiguous title + software word in title"
    if sw >= 3 and sw > nsw:
        return True, f"ambiguous title + software description (sw={sw}, non-sw={nsw})"
    return False, f"ambiguous title without software context (sw={sw}, non-sw={nsw})"


# ── Role type (for the output column) ───────────────────────────────────────
_ROLE_TYPES = [
    ("Management", r"\b(head|director|vp|chief|manager|management)\b"),
    ("Lead", r"\b(lead|principal|staff|architect)\b"),
    ("Performance", r"\b(performance|load|stress|jmeter|gatling|k6|loadrunner)\b"),
    ("Game QA", r"\b(game|games|gaming|playtest|console|video ?game|lqa)\b"),
    ("Mobile QA", r"\b(mobile|ios|android|appium|xcuitest|espresso|detox)\b"),
    ("Automation / SDET", r"\b(sdet|automation|automated|in test|selenium|playwright|cypress|webdriver|"
                          r"testng|cucumber|katalon|robot framework|rest ?assured|pytest)\b"),
    ("Manual QA", r"\b(manual|functional|uat|user acceptance|tester)\b"),
]


def role_type(title: str) -> str:
    for name, pat in _ROLE_TYPES:
        if re.search(pat, title or "", _I):
            return name
    return "QA (general)"
