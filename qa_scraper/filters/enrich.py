"""Derive extra columns from the posting text. Conservative: blank when unsure."""
from __future__ import annotations

import re

from ..models import Job
from .qa_match import role_type

_I = re.IGNORECASE

TOOLS = {
    "Selenium": r"\bselenium\b", "Playwright": r"\bplaywright\b", "Cypress": r"\bcypress\b",
    "Appium": r"\bappium\b", "WebdriverIO": r"\bwebdriver ?io\b|\bwdio\b", "TestNG": r"\btestng\b",
    "JUnit": r"\bjunit\b", "Pytest": r"\bpytest\b", "Jest": r"\bjest\b", "Mocha": r"\bmocha\b",
    "Cucumber/BDD": r"\bcucumber\b|\bgherkin\b|\bbdd\b", "Robot Framework": r"\brobot framework\b",
    "Katalon": r"\bkatalon\b", "Postman": r"\bpostman\b", "REST Assured": r"\brest[- ]?assured\b",
    "SoapUI": r"\bsoap ?ui\b", "JMeter": r"\bjmeter\b", "Gatling": r"\bgatling\b", "k6": r"\bk6\b",
    "Locust": r"\blocust\b", "LoadRunner": r"\bloadrunner\b", "TestRail": r"\btestrail\b",
    "Zephyr": r"\bzephyr\b", "Xray": r"\bxray\b", "Jira": r"\bjira\b", "Jenkins": r"\bjenkins\b",
    "GitHub Actions": r"\bgithub actions\b", "GitLab CI": r"\bgitlab[- ]ci\b", "Docker": r"\bdocker\b",
    "Kubernetes": r"\bkubernetes\b|\bk8s\b", "BrowserStack": r"\bbrowserstack\b",
    "Sauce Labs": r"\bsauce ?labs\b", "XCUITest": r"\bxcuitest\b", "Espresso": r"\bespresso\b",
    "Detox": r"\bdetox\b", "TestCafe": r"\btest ?cafe\b", "Tosca": r"\btosca\b",
    "TestComplete": r"\btestcomplete\b", "Ranorex": r"\branorex\b", "UFT/QTP": r"\buft\b|\bqtp\b",
    "SQL": r"\bsql\b", "Python": r"\bpython\b", "Java": r"\bjava\b(?!script)",
    "JavaScript": r"\bjavascript\b", "TypeScript": r"\btypescript\b", "C#": r"(?<!\w)c#",
    "ISTQB": r"\bistqb\b", "AWS": r"\baws\b",
}
_TOOLS = [(name, re.compile(p, _I)) for name, p in TOOLS.items()]

_SENIORITY = [
    ("Director+", r"\b(director|vp|vice president|head of|chief)\b"),
    ("Manager", r"\bmanager\b"),
    ("Lead / Principal", r"\b(lead|principal|staff|architect)\b"),
    ("Senior", r"\b(s[eéê]nior|sr\.?|iii|iv)\b"),
    ("Intern", r"\b(intern|internship|trainee|apprentice|working student|werkstudent)\b"),
    ("Junior", r"\b(junior|jr\.?|entry[- ]level|graduate|associate|i)\b"),
    ("Mid", r"\b(mid|intermediate|ii)\b"),
]
_EXPERIENCE = re.compile(
    r"(?<![\d.])(\d{1,2})\s*(?:\+|plus)?\s*(?:(?:-|to|–)\s*(\d{1,2}))?\s*\+?\s*years?(?:'|’)?\s*(?:of\s+)?"
    r"(?:\w+\s+){0,4}?(?:experience|exp\b)", _I)
_SALARY_TEXT = re.compile(
    r"(?:[$€£]|USD|EUR|GBP|CAD|AUD|PKR|INR|Rs\.?)\s?\d[\d,.]*\s?[kK]?"
    r"(?:\s*(?:-|–|to)\s*(?:[$€£]|USD|EUR|GBP|CAD|AUD|PKR|INR|Rs\.?)?\s?\d[\d,.]*\s?[kK]?)?"
    r"(?:\s*(?:per|/|a)\s*(?:year|yr|annum|month|mo|hour|hr))?")
_REMOTE = [("Hybrid", r"\bhybrid\b"), ("Remote", r"\b(remote|work from home|wfh|anywhere|distributed)\b"),
           ("Onsite", r"\b(on[- ]?site|in[- ]office|office[- ]based)\b")]

COUNTRIES = [
    "United States", "Canada", "Mexico", "Brazil", "Argentina", "Chile", "Colombia", "Peru", "Uruguay",
    "Costa Rica", "United Kingdom", "Ireland", "Germany", "France", "Spain", "Portugal", "Italy",
    "Netherlands", "Belgium", "Luxembourg", "Switzerland", "Austria", "Poland", "Czech Republic",
    "Czechia", "Slovakia", "Hungary", "Romania", "Bulgaria", "Greece", "Croatia", "Serbia", "Slovenia",
    "Ukraine", "Lithuania", "Latvia", "Estonia", "Finland", "Sweden", "Norway", "Denmark", "Iceland",
    "Turkey", "Israel", "United Arab Emirates", "Saudi Arabia", "Qatar", "Egypt", "Morocco", "Nigeria",
    "Kenya", "South Africa", "Ghana", "Pakistan", "India", "Bangladesh", "Sri Lanka", "Nepal",
    "China", "Hong Kong", "Taiwan", "Japan", "South Korea", "Singapore", "Malaysia", "Indonesia",
    "Philippines", "Vietnam", "Thailand", "Australia", "New Zealand", "Armenia", "Cyprus", "Malta",
    # "Georgia" deliberately omitted: it is far more often the US state.
]
_COUNTRY_ALIASES = {
    "usa": "United States", "us": "United States", "u.s.": "United States", "united states of america": "United States",
    "uk": "United Kingdom", "gb": "United Kingdom", "england": "United Kingdom", "scotland": "United Kingdom",
    "uae": "United Arab Emirates", "dubai": "United Arab Emirates", "abu dhabi": "United Arab Emirates",
    "deutschland": "Germany", "korea": "South Korea", "czechia": "Czech Republic", "ksa": "Saudi Arabia",
}
_ISO2 = {
    "US": "United States", "CA": "Canada", "MX": "Mexico", "BR": "Brazil", "AR": "Argentina", "CL": "Chile",
    "CO": "Colombia", "GB": "United Kingdom", "UK": "United Kingdom", "IE": "Ireland", "DE": "Germany",
    "FR": "France", "ES": "Spain", "PT": "Portugal", "IT": "Italy", "NL": "Netherlands", "BE": "Belgium",
    "CH": "Switzerland", "AT": "Austria", "PL": "Poland", "CZ": "Czech Republic", "HU": "Hungary",
    "RO": "Romania", "BG": "Bulgaria", "GR": "Greece", "UA": "Ukraine", "LT": "Lithuania", "EE": "Estonia",
    "FI": "Finland", "SE": "Sweden", "NO": "Norway", "DK": "Denmark", "TR": "Turkey", "IL": "Israel",
    "AE": "United Arab Emirates", "SA": "Saudi Arabia", "EG": "Egypt", "NG": "Nigeria", "KE": "Kenya",
    "ZA": "South Africa", "PK": "Pakistan", "IN": "India", "BD": "Bangladesh", "LK": "Sri Lanka",
    "CN": "China", "HK": "Hong Kong", "TW": "Taiwan", "JP": "Japan", "KR": "South Korea", "SG": "Singapore",
    "MY": "Malaysia", "ID": "Indonesia", "PH": "Philippines", "VN": "Vietnam", "TH": "Thailand",
    "AU": "Australia", "NZ": "New Zealand", "USA": "United States", "GBR": "United Kingdom",
    "CAN": "Canada", "DEU": "Germany", "IND": "India", "PAK": "Pakistan", "AUS": "Australia",
}
_US_STATES = ("AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM "
              "NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC").split()
_US_STATE_RE = re.compile(r",\s*(" + "|".join(_US_STATES) + r")\b")
_CITIES = {
    "new york": "United States", "san francisco": "United States", "seattle": "United States",
    "austin": "United States", "boston": "United States", "chicago": "United States", "los angeles": "United States",
    "london": "United Kingdom", "manchester": "United Kingdom", "berlin": "Germany", "munich": "Germany",
    "hamburg": "Germany", "paris": "France", "madrid": "Spain", "barcelona": "Spain", "lisbon": "Portugal",
    "amsterdam": "Netherlands", "dublin": "Ireland", "warsaw": "Poland", "krakow": "Poland", "prague": "Czech Republic",
    "bucharest": "Romania", "kyiv": "Ukraine", "stockholm": "Sweden", "copenhagen": "Denmark", "oslo": "Norway",
    "helsinki": "Finland", "zurich": "Switzerland", "tel aviv": "Israel", "toronto": "Canada", "vancouver": "Canada",
    "montreal": "Canada", "bangalore": "India", "bengaluru": "India", "hyderabad": "India", "pune": "India",
    "chennai": "India", "mumbai": "India", "gurgaon": "India", "gurugram": "India", "noida": "India",
    "delhi": "India", "lahore": "Pakistan", "karachi": "Pakistan", "islamabad": "Pakistan",
    "rawalpindi": "Pakistan", "singapore": "Singapore", "tokyo": "Japan", "sydney": "Australia",
    "melbourne": "Australia", "sao paulo": "Brazil", "são paulo": "Brazil", "mexico city": "Mexico",
    "buenos aires": "Argentina", "bogota": "Colombia", "bogotá": "Colombia", "cairo": "Egypt", "lagos": "Nigeria",
    "nairobi": "Kenya", "cape town": "South Africa", "manila": "Philippines", "ho chi minh": "Vietnam",
    "kuala lumpur": "Malaysia", "jakarta": "Indonesia", "istanbul": "Turkey", "athens": "Greece",
    "riyadh": "Saudi Arabia", "doha": "Qatar", "dhaka": "Bangladesh", "colombo": "Sri Lanka",
}
_COUNTRY_RE = re.compile(r"\b(" + "|".join(re.escape(c) for c in sorted(COUNTRIES, key=len, reverse=True)) + r")\b", _I)
_CITY_RE = [(re.compile(r"\b" + re.escape(city) + r"\b", _I), country) for city, country in _CITIES.items()]
_US_STATE_NAMES = (
    "Alabama Alaska Arizona Arkansas California Colorado Connecticut Delaware Florida Georgia Hawaii Idaho "
    "Illinois Indiana Iowa Kansas Kentucky Louisiana Maine Maryland Massachusetts Michigan Minnesota "
    "Mississippi Missouri Montana Nebraska Nevada Ohio Oklahoma Oregon Pennsylvania Tennessee Texas Utah "
    "Vermont Virginia Wisconsin Wyoming").split() + [
    "New Hampshire", "New Jersey", "New Mexico", "North Carolina", "North Dakota", "Rhode Island",
    "South Carolina", "South Dakota", "West Virginia", "Washington DC", "Washington, D.C."]
# Only after a comma ("Atlanta, Georgia"), so the country Georgia ("Tbilisi") is not mistaken.
_US_STATE_NAME_RE = re.compile(r",\s*(" + "|".join(re.escape(s) for s in _US_STATE_NAMES) + r")\b", _I)


def country_from(location: str, hint: str = "") -> str:
    """Best-effort country list from a location string ('; '-joined when several)."""
    found: list[str] = []
    for h in (hint or "").split(";"):
        h = h.strip()
        if h:
            found.append(_ISO2.get(h.upper(), _COUNTRY_ALIASES.get(h.lower(), h if len(h) > 3 else "")))
    loc = location or ""
    for m in _COUNTRY_RE.finditer(loc):
        name = next(c for c in COUNTRIES if c.lower() == m.group(1).lower())
        found.append("Czech Republic" if name == "Czechia" else name)
    for part in re.split(r"[;,/|()\-–]", loc):
        p = part.strip().lower()
        if p in _COUNTRY_ALIASES:
            found.append(_COUNTRY_ALIASES[p])
        elif p.upper() in ("USA", "UK", "UAE"):
            found.append(_ISO2.get(p.upper(), _COUNTRY_ALIASES.get(p)))
    if _US_STATE_RE.search(loc) or _US_STATE_NAME_RE.search(loc):
        found.append("United States")
    for rx, country in _CITY_RE:
        if rx.search(loc):
            found.append(country)
    out = list(dict.fromkeys(f for f in found if f))
    return "; ".join(out)      # full list: the "can I apply from X" rule needs every country


# Statements in a description that contradict a "Remote" label (the role needs office time).
_NOT_REMOTE = re.compile(
    r"\b((?<!remote or )(?<!remote/)hybrid (role|position|model|schedule|arrangement|setup|set-up|basis)"
    r"|(work(ing)? arrangement|work model|workplace type|work type|location type)\s*:?\s*hybrid"
    r"|(this|the) (role|position|job) is (a )?hybrid"
    r"|\d\s*(\+\s*)?days? (a|per|each) week (in|at|from) (the |our )?(office|site|hq)"
    r"|(in|at) (the |our )?office \d\s*(\+\s*)?days?"
    r"|(on[- ]?site|in[- ]office|in[- ]person) (role|position|job|presence|requirement)"
    r"|(this|the) (role|position|job) is (based )?(on[- ]?site|in[- ]office|in[- ]person)"
    r"|not (a )?remote|no remote|remote work is not|commuting distance)\b", re.I)


def remote_from(job: Job) -> str:
    if job.remote_type:
        if job.remote_type == "Remote" and job.description:
            m = _NOT_REMOTE.search(job.description)
            if m:                                   # labelled remote, but the text says otherwise
                return "Hybrid" if "hybrid" in m.group(0).lower() or "days" in m.group(0).lower() else "Onsite"
        return job.remote_type
    head = f"{job.title} {job.location}"
    for name, pat in _REMOTE:
        if re.search(pat, head, _I):
            return name
    # description: only trust explicit statements
    m = re.search(r"\b(this (is a|role is|position is) (fully )?(remote|hybrid))\b|\b(fully remote|100% remote|remote[- ]first)\b"
                  r"|\b100% (wfh|work from home)\b|\bwork arrangement:\s*(remote|hybrid)\b|\bremote work is authori[sz]ed\b"
                  r"|\bnationwide remote\b",
                  job.description or "", _I)
    if m:
        return "Hybrid" if "hybrid" in m.group(0).lower() else "Remote"
    return ""


def seniority_from(title: str) -> str:
    for name, pat in _SENIORITY:
        if re.search(pat, title or "", _I):
            return name
    return ""


SENIOR_LEVELS = ("Director+", "Manager", "Lead / Principal", "Senior")


def excluded_country(country: str, location: str, excluded: list[str]) -> bool:
    """True when the job is only open in an excluded country (e.g. India). Region-wide
    lists of more than 3 countries are not excluded for containing one of them."""
    if not excluded:
        return False
    places = [p.strip() for p in re.split(r"[;,|/]", f"{country}") if p.strip()]
    many = len(places) > 3 or "more)" in (country or "")
    text = f"{country} {location}"
    hit = any(re.search(r"\b" + re.escape(c) + r"\b", text, _I) for c in excluded)
    return hit and not many


_WORLDWIDE = re.compile(r"\b(worldwide|world[- ]wide|anywhere(?! in\b)|global(ly)?|any (country|location)|"
                        r"work from anywhere|all countries|international)\b", _I)
_JUST_REMOTE = re.compile(r"^\s*(\(?(fully |100% )?remote( job| position| role| work)?\)?|wfh|work from home|"
                          r"telecommute|virtual|not specified)?\s*$", _I)
# Description phrases that limit a remote job to certain places.
_RESTRICTED = re.compile(
    r"\b(us|u\.s\.?|usa|united states|canada|canadian|uk|united kingdom|eu|europe(an)?|latam|latin america|"
    r"north america|americas|australia|new zealand|germany|brazil|mexico)[- ]?(only|based( only)?|residents?)\b"
    r"|\bmust (be|reside|live)( located| based)? (in|within)\b"
    r"|\b(authori[sz]ed|eligible|permitted|legally able) to work (in|within|for)\b"
    r"|\b(work|employment) (authori[sz]ation|eligibility|permit) (in|for)\b"
    r"|\bresidents? of (the )?(us|u\.s\.|usa|united states|canada|uk|united kingdom|eu|europe|australia)\b"
    r"|\b(located|based|reside|living) in (the )?(us|u\.s\.|usa|united states|canada|uk|united kingdom|eu|"
    r"european union|europe|latam|latin america|north america|australia|one of the following)\b"
    r"|\bwithin the (us|u\.s\.|usa|united states|continental|contiguous|uk|eu|european union)\b"
    r"|\b(us|u\.s\.) (citizen(ship)?|person|clearance)\b|\bsecurity clearance\b|\bpublic trust\b"
    r"|\bvisa sponsorship is not\b|\bno visa sponsorship\b", _I)


def open_to(country: str, location: str, description: str, home: str, regions: list[str]) -> bool:
    """Can someone living in `home` apply to this remote job?

    Yes when the job is worldwide, names `home`, or names a region that contains it
    (Asia, APAC...). No when it lists other countries, cities or regions only. When it
    names no place at all, yes unless the description limits it ("US only", "must be
    authorized to work in the US", "security clearance")."""
    if not home:
        return True
    places = f"{country or ''} | {location or ''}"
    if re.search(r"\b" + re.escape(home) + r"\b", places, _I):
        return True
    if _WORLDWIDE.search(places) or any(re.search(r"\b" + re.escape(r) + r"\b", places, _I) for r in regions):
        return True
    if (country or "").strip() or not _JUST_REMOTE.match(location or ""):
        return False                         # names somewhere else
    desc = description or ""
    if re.search(r"\b" + re.escape(home) + r"\b", desc, _I):
        return True
    return not _RESTRICTED.search(desc)


def too_senior_title(title: str) -> bool:
    return seniority_from(title) in SENIOR_LEVELS


def min_years(experience: str) -> int | None:
    m = re.match(r"(\d+)", experience or "")
    return int(m.group(1)) if m else None


def experience_from(description: str) -> str:
    best = None
    for m in _EXPERIENCE.finditer(description or ""):
        lo, hi = int(m.group(1)), m.group(2)
        if lo > 15:                 # "30+ years of experience" is about the company, not the job
            continue
        cand = f"{lo}-{int(hi)} years" if hi else f"{lo}+ years"
        if best is None:
            best = cand
    return best or ""


def tools_from(text: str) -> str:
    return ", ".join(name for name, rx in _TOOLS if rx.search(text or ""))


_PAY_WORDS = re.compile(r"(salary|compensation|pay|base|range|ctc|lpa|per (year|annum|month|hour)|"
                        r"annual|hourly|monthly|gross|net|/ ?(yr|year|hr|hour|month))", _I)


def salary_from(description: str) -> str:
    """Only accept a money figure with a pay word right next to it, so funding
    rounds ("raised $50,000,000") and revenue figures are not mistaken for pay."""
    text = description or ""
    for m in _SALARY_TEXT.finditer(text):
        s = m.group(0).strip()
        digits = re.sub(r"\D", "", s)
        if not (len(digits) >= 4 or re.search(r"\d\s?[kK]\b", s)):
            continue
        window = text[max(0, m.start() - 80): m.end() + 30]
        if _PAY_WORDS.search(window) and not re.search(r"\b(raised|funding|revenue|valuation|series [a-e])\b", window, _I):
            return s
    return ""


def enrich(job: Job) -> None:
    text = f"{job.title}\n{job.description}"
    job.role_type = role_type(job.title)
    job.seniority = seniority_from(job.title)
    job.experience = job.experience or experience_from(job.description)
    job.tools = tools_from(text)
    job.remote_type = remote_from(job)
    offices = "; ".join(job.detail_ref.get("offices") or [])
    job.country = country_from(f"{job.location}; {offices}", job.country)
    if not job.salary:
        job.salary = salary_from(job.description)
