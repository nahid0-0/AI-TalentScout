import asyncio
import json
import logging
import random
import re
from pathlib import Path

from playwright.async_api import async_playwright, Page

from models import (
    ProfileData, Experience, Education, Honor, Project,
    Publication, Certification, Recommendation, Volunteer,
    Patent, SkillItem, TrajectoryAnalysis
)

logger = logging.getLogger("li_scraper")

COOKIES_PATH = Path(__file__).parent / "cookies.json"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:152.0) Gecko/20100101 Firefox/152.0"

# If LinkedIn redirects to any of these, we stop the whole run immediately
# rather than continuing to hammer a flagged/logged-out session.
CHECKPOINT_MARKERS = ["/checkpoint/", "/authwall", "/login"]

# Phrases LinkedIn injects into list items / section chrome that are not
# actual content. Anything containing these (case-insensitive) gets dropped.
JUNK_PHRASES = [
    "show all", "show credential", "show details", "endorse", "endorsed by",
    "helped you discover", "skip to", "see more", "see less", "load more",
    "...", "loading", "this section",
]


class CircuitBreakerTripped(Exception):
    """Raised when LinkedIn shows a login wall / checkpoint mid-run."""


def load_cookies() -> list[dict]:
    if not COOKIES_PATH.exists():
        raise FileNotFoundError(
            f"No cookies.json found at {COOKIES_PATH}. "
            "Export your LinkedIn cookies (JSON format) into that file before running."
        )
    with open(COOKIES_PATH, "r") as f:
        raw_cookies = json.load(f)

    cleaned = []
    for c in raw_cookies:
        same_site = c.get("sameSite")
        if same_site not in ("Strict", "Lax", "None"):
            same_site = "Lax"
        domain = c.get("domain", "")
        if not domain and "url" in c:
            domain = ".linkedin.com"
        cleaned.append({
            "name": c["name"],
            "value": c["value"].strip('"') if isinstance(c["value"], str) else c["value"],
            "domain": domain or ".linkedin.com",
            "path": c.get("path", "/"),
            "secure": c.get("secure", True),
            "httpOnly": c.get("httpOnly", False),
            "sameSite": same_site,
        })
    return cleaned


async def _check_checkpoint(page: Page):
    url = page.url
    if any(marker in url for marker in CHECKPOINT_MARKERS):
        raise CircuitBreakerTripped(
            f"Hit a login/checkpoint redirect ({url}). Stopping run to avoid further account risk."
        )


async def _safe_text(page, selector: str) -> str | None:
    try:
        el = await page.query_selector(selector)
        if el:
            text = await el.inner_text()
            return text.strip() or None
    except Exception:
        pass
    return None


def _is_junk(line: str) -> bool:
    """True if a line is LinkedIn UI chrome rather than real content."""
    if not line or not line.strip():
        return True
    lower = line.strip().lower()
    if len(lower) < 2:
        return True
    return any(phrase in lower for phrase in JUNK_PHRASES)


def _clean_lines(raw_text: str) -> list[str]:
    """Split a block of inner_text into deduped, junk-filtered lines."""
    lines = [l.strip() for l in raw_text.split("\n") if l.strip()]
    cleaned = []
    for line in lines:
        if _is_junk(line):
            continue
        # LinkedIn duplicates the same line for visually-hidden + aria-hidden
        # spans; collapse consecutive exact dupes.
        if cleaned and cleaned[-1] == line:
            continue
        cleaned.append(line)
    return cleaned


_DURATION_RE = re.compile(
    r"(\d{4}|present)\s*[-–]\s*(\d{4}|present)|"
    r"\b\d+\s*(yr|yrs|year|years|mo|mos|month|months)\b",
    re.IGNORECASE,
)


def _looks_like_duration(line: str) -> bool:
    return bool(_DURATION_RE.search(line))


async def _find_section(page: Page, heading_keywords: list[str], section_id: str | None = None):
    sections = await page.query_selector_all("section, div.pv-profile-card, div.profile-detail-card")
    for sec in sections:
        sec_id = await sec.get_attribute("id") or ""
        if section_id and sec_id == section_id:
            return sec
        headings = await sec.query_selector_all("h2, h3, span.text-heading-large, .pvs-header__title")
        for h in headings:
            h_text = (await h.inner_text()).strip().lower()
            if any(kw.lower() in h_text for kw in heading_keywords):
                return sec
    return None


async def _parse_list_section(sec, max_items: int = 35) -> list[list[str]]:
    """
    Returns cleaned line-groups, one per <li> or entity container, for a generic LinkedIn
    list-based section (education, honors, projects, etc).
    """
    items = []
    lis = await sec.query_selector_all("li, .artdeco-list__item, .pvs-entity")
    for li in lis[:max_items]:
        txt = await li.inner_text()
        lines = _clean_lines(txt)
        if lines:
            items.append(lines)
    return items


async def _parse_education(sec) -> list[Education]:
    results = []
    for lines in await _parse_list_section(sec):
        school = lines[0] if len(lines) > 0 else None
        degree, field, duration, desc_lines = None, None, None, []
        for line in lines[1:]:
            if _looks_like_duration(line) and not duration:
                duration = line
            elif "," in line and not degree:
                degree, field = [p.strip() for p in line.split(",", 1)]
            elif not degree:
                degree = line
            else:
                desc_lines.append(line)
        results.append(Education(
            school=school, degree=degree, field=field, duration=duration,
            description=" ".join(desc_lines) or None,
        ))
    return results


async def _parse_honors(sec) -> list[Honor]:
    results = []
    for lines in await _parse_list_section(sec):
        title = lines[0] if len(lines) > 0 else None
        issuer, date, desc_lines = None, None, []
        for line in lines[1:]:
            if _looks_like_duration(line) or re.search(r"\b(19|20)\d{2}\b", line):
                if not date:
                    date = line
                    continue
            if line.lower().startswith("issued by") or (not issuer and not date):
                issuer = line.replace("Issued by ", "").strip()
            else:
                desc_lines.append(line)
        results.append(Honor(
            title=title, issuer=issuer, date=date,
            description=" ".join(desc_lines) or None,
        ))
    return results


async def _parse_projects(sec) -> list[Project]:
    results = []
    for lines in await _parse_list_section(sec):
        title = lines[0] if len(lines) > 0 else None
        duration, desc_lines = None, []
        for line in lines[1:]:
            if _looks_like_duration(line) and not duration:
                duration = line
            else:
                desc_lines.append(line)
        results.append(Project(
            title=title, duration=duration,
            description=" ".join(desc_lines) or None,
        ))
    return results


async def _parse_publications(sec) -> list[Publication]:
    results = []
    for lines in await _parse_list_section(sec):
        title = lines[0] if len(lines) > 0 else None
        publisher, date, desc_lines = None, None, []
        for line in lines[1:]:
            if re.search(r"\b(19|20)\d{2}\b", line) and not date:
                date = line
            elif not publisher:
                publisher = line
            else:
                desc_lines.append(line)
        results.append(Publication(
            title=title, publisher=publisher, date=date,
            description=" ".join(desc_lines) or None,
        ))
    return results


async def _parse_certifications(sec) -> list[Certification]:
    results = []
    for lines in await _parse_list_section(sec):
        title = lines[0] if len(lines) > 0 else None
        issuer, date = None, None
        for line in lines[1:]:
            if re.search(r"\b(19|20)\d{2}\b", line) and not date:
                date = line
            elif not issuer:
                issuer = line
        results.append(Certification(title=title, issuer=issuer, date=date))
    return results


async def _parse_patents(sec) -> list[Patent]:
    results = []
    for lines in await _parse_list_section(sec):
        title = lines[0] if len(lines) > 0 else None
        issuer, date, desc_lines = None, None, []
        for line in lines[1:]:
            if re.search(r"\b(19|20)\d{2}\b", line) and not date:
                date = line
            elif not issuer:
                issuer = line
            else:
                desc_lines.append(line)
        results.append(Patent(
            title=title, issuer=issuer, date=date,
            description=" ".join(desc_lines) or None,
        ))
    return results


async def _parse_volunteer(sec) -> list[Volunteer]:
    results = []
    for lines in await _parse_list_section(sec):
        role = lines[0] if len(lines) > 0 else None
        org, duration, desc_lines = None, None, []
        for line in lines[1:]:
            if _looks_like_duration(line) and not duration:
                duration = line
            elif not org:
                org = line
            else:
                desc_lines.append(line)
        results.append(Volunteer(
            role=role, organization=org, duration=duration,
            description=" ".join(desc_lines) or None,
        ))
    return results


async def _parse_recommendations(sec) -> list[Recommendation]:
    results = []
    for lines in await _parse_list_section(sec, max_items=15):
        if len(lines) < 2:
            continue
        recommender = lines[0]
        relationship = lines[1] if len(lines) > 2 else None
        text_lines = lines[2:] if relationship else lines[1:]
        results.append(Recommendation(
            recommender=recommender, relationship=relationship,
            text=" ".join(text_lines) or None,
        ))
    return results


async def _parse_languages(sec) -> list[str]:
    langs = []
    for lines in await _parse_list_section(sec):
        if lines:
            langs.append(lines[0])
    return langs


async def scrape_profile(page: Page, url: str) -> ProfileData:
    data = ProfileData(url=url)
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await _check_checkpoint(page)

        try:
            await page.wait_for_selector("h1", timeout=10000)
        except Exception:
            pass

        # --- Identity / top card ---
        data.name = await _safe_text(page, "h1.text-heading-xlarge") or await _safe_text(page, "h1")
        data.headline = (
            await _safe_text(page, "div.text-body-medium.break-words")
            or await _safe_text(page, "div.text-body-medium")
        )
        data.location = (
            await _safe_text(page, "span.text-body-small.inline.t-black--light.break-words")
            or await _safe_text(page, "span.text-body-small")
        )

        top_sec = await page.query_selector("main section")
        if top_sec and (not data.name or not data.headline or not data.location):
            top_text = await top_sec.inner_text()
            lines = _clean_lines(top_text)
            if lines:
                if not data.name and len(lines) > 0:
                    data.name = lines[0]
                if not data.headline and len(lines) > 1:
                    data.headline = lines[1]
                if not data.location:
                    for line in lines[2:6]:
                        if any(kw in line.lower() for kw in [
                            "area", "united", "bangladesh", "state", "city",
                            "county", "country", "bay"
                        ]):
                            data.location = line
                            break

        # Follower / connection counts often sit near the top card as plain text
        full_top_text = (await top_sec.inner_text()) if top_sec else ""
        follower_match = re.search(r"([\d,.]+[KkMm]?)\s+followers", full_top_text)
        connection_match = re.search(r"([\d,.]+\+?)\s+connections", full_top_text)
        if follower_match:
            data.follower_count = follower_match.group(1)
        if connection_match:
            data.connection_count = connection_match.group(1)

        # --- Lazy-load hydration: scroll the full page so every section renders ---
        try:
            for _ in range(12):
                await page.evaluate("window.scrollBy(0, 900)")
                await asyncio.sleep(0.8)
        except Exception:
            pass

        # --- About ---
        about_sec = await _find_section(page, ["about"], section_id="about")
        if about_sec:
            lines = _clean_lines(await about_sec.inner_text())
            if len(lines) > 1:
                data.about = " ".join(lines[1:])

        # --- Experience ---
        exp_sec = await _find_section(page, ["experience"], section_id="experience")
        if exp_sec:
            experiences = []
            for lines in await _parse_list_section(exp_sec):
                if not lines or len(lines[0]) > 90:
                    continue
                title = lines[0]
                company, duration, location, desc_lines = None, None, None, []
                for line in lines[1:]:
                    if _looks_like_duration(line) and not duration:
                        duration = line
                    elif not company and not any(k in line for k in ["Full-time", "Part-time", "Contract"]):
                        company = line
                    elif not location and any(k in line.lower() for k in ["remote", "hybrid", "on-site", ",", "area"]):
                        location = line
                    else:
                        desc_lines.append(line)
                experiences.append(Experience(
                    title=title, company=company, duration=duration,
                    location=location, description=" ".join(desc_lines) or None,
                ))
            if experiences:
                data.experience = experiences

        # --- Skills ---
        skills_sec = await _find_section(page, ["skills"], section_id="skills")
        if skills_sec:
            skills = []
            for lines in await _parse_list_section(skills_sec):
                if lines and len(lines[0]) < 60:
                    skills.append(lines[0])
            if skills:
                data.skills = skills

        # --- Education ---
        edu_sec = await _find_section(page, ["education"], section_id="education")
        if edu_sec:
            data.education = await _parse_education(edu_sec)

        # --- Honors & Awards ---
        honors_sec = await _find_section(page, ["honors", "awards"], section_id="honors_and_awards")
        if honors_sec:
            data.honors = await _parse_honors(honors_sec)

        # --- Projects ---
        proj_sec = await _find_section(page, ["projects"], section_id="projects")
        if proj_sec:
            data.projects = await _parse_projects(proj_sec)

        # --- Publications ---
        pub_sec = await _find_section(page, ["publications"], section_id="publications")
        if pub_sec:
            data.publications = await _parse_publications(pub_sec)

        # --- Certifications ---
        cert_sec = await _find_section(
            page, ["licenses", "certifications"], section_id="licenses_and_certifications"
        )
        if cert_sec:
            data.certifications = await _parse_certifications(cert_sec)

        # --- Patents ---
        patents_sec = await _find_section(page, ["patents"], section_id="patents")
        if patents_sec:
            data.patents = await _parse_patents(patents_sec)

        # --- Volunteer experience ---
        vol_sec = await _find_section(page, ["volunteer"], section_id="volunteering_experience")
        if vol_sec:
            data.volunteer = await _parse_volunteer(vol_sec)

        # --- Recommendations ---
        rec_sec = await _find_section(page, ["recommendations"], section_id="recommendations")
        if rec_sec:
            data.recommendations = await _parse_recommendations(rec_sec)

        # --- Languages ---
        lang_sec = await _find_section(page, ["languages"], section_id="languages")
        if lang_sec:
            data.languages = await _parse_languages(lang_sec)

    except CircuitBreakerTripped:
        raise
    except Exception as e:
        logger.exception(f"Failed scraping {url}")
        data.error = str(e)

    return data


async def run_scrape_job(
    profile_urls: list[str],
    min_wait: int,
    max_wait: int,
    on_result=None,
) -> list[ProfileData]:
    """
    Sequentially scrapes each profile in one browser context (one session),
    with a randomized delay between each — deliberately not concurrent.
    Stops immediately if a login/checkpoint wall is detected.
    """
    cookies = load_cookies()
    results: list[ProfileData] = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(user_agent=USER_AGENT)
        await context.add_cookies(cookies)
        page = await context.new_page()

        try:
            for i, url in enumerate(profile_urls):
                logger.info(f"Scraping {i + 1}/{len(profile_urls)}: {url}")
                result = await scrape_profile(page, url)
                results.append(result)
                if on_result:
                    await on_result(result)

                if i < len(profile_urls) - 1:
                    delay = random.uniform(min_wait, max_wait)
                    logger.info(f"Waiting {delay:.1f}s before next profile...")
                    await asyncio.sleep(delay)

        except CircuitBreakerTripped as e:
            logger.warning(str(e))
            raise
        finally:
            await context.close()
            await browser.close()

    return results
