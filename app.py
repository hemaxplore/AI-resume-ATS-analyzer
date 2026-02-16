import streamlit as st
import re
import plotly.graph_objects as go
import io

import pdfplumber
from docx import Document

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.styles import ParagraphStyle

# --------------------------------------------------
# PAGE CONFIG
# --------------------------------------------------
st.set_page_config(
    page_title="AI Resume ATS Analyzer",
    page_icon="📄",
    layout="wide"
)

# --------------------------------------------------
# SAFE SESSION INIT
# --------------------------------------------------
defaults = {
    "analyzed": False,
    "resume": None,
    "jd": None,
    "confirm_reset": False,
    "form_version": 0
}

for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

if st.session_state.form_version is None:
    st.session_state.form_version = 0 
    
if "recruiter_mode" not in st.session_state:
    st.session_state.recruiter_mode = False 

# --------------------------------------------------
# RESUME TEXT EXTRACTION (FIXED)
# --------------------------------------------------
def extract_text_from_pdf(file):
    text = ""
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            text += page.extract_text() or ""
    return text


def extract_text_from_docx(file):
    doc = Document(file)
    return "\n".join([p.text for p in doc.paragraphs])



# --------------------------------------------------
# CLEAN + NORMALIZE TEXT  (FINAL STABLE VERSION)
# --------------------------------------------------
def clean_resume_text(text):

    if not text:
        return ""

    # normalize line endings
    text = text.replace("\r", "\n")

    # ---------- FORCE HEADER BREAKS ----------
    headers = [
        "PROFESSIONAL SUMMARY",
        "SUMMARY",
        "EDUCATION",
        "INTERNSHIP EXPERIENCE",
        "INTERNSHIP",
        "PROJECTS",
        "PROJECT EXPERIENCE",
        "ACADEMIC PROJECTS",
        "PERSONAL PROJECTS",
        "TECHNICAL SKILLS",
        "SKILLS",
        "CERTIFICATIONS"
    ]

    # 🔥 IMPORTANT:
    # Add newline ONLY if header is attached to sentence
    for h in headers:
        text = re.sub(
            rf"(?<!\n){h}",
            f"\n\n{h}",
            text,
            flags=re.IGNORECASE
        )

    # ---------- FIX BULLETS ----------
    text = re.sub(r"[•●▪]", "\n• ", text)

    # ---------- REMOVE EXTRA SPACES ----------
    text = re.sub(r"[ \t]+", " ", text)

    # ---------- CLEAN MULTIPLE NEWLINES ----------
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()

# --------------------------------------------------
# ✅ BULLETPROOF SECTION EXTRACTOR (FINAL FIX)
# --------------------------------------------------
def extract_section(text, section_name):

    if not text:
        return ""

    # normalize
    text = text.replace("\r", "")

    # known section headers only
    headers = [
        "PROFESSIONAL SUMMARY",
        "EDUCATION",
        "INTERNSHIP EXPERIENCE",
        "PROJECTS",
        "TECHNICAL SKILLS",
        "CORE SKILLS",
        "SKILLS"
    ]

    # build boundary regex ONLY using REAL headers
    header_pattern = "|".join(headers)

    pattern = re.compile(
        rf"{section_name}\s*\n(.*?)(?=\n(?:{header_pattern})\n|\Z)",
        re.IGNORECASE | re.DOTALL
    )

    match = pattern.search(text)

    return match.group(1).strip() if match else ""

# --------------------------------------------------
# USER DETAILS
# --------------------------------------------------

def extract_user_details(text):
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    # ---------------- NAME EXTRACTION ----------------
    name = "Name not found"
    blacklist = {
        "engineer", "developer", "student", "fresher",
        "software", "email", "phone", "mobile",
        "linkedin", "github", "resume", "curriculum", "vitae"
    }

    for line in lines[:10]:
        words = line.split()
        if (
            2 <= len(words) <= 4
            and not re.search(r"\d|@", line)
            and not any(b in line.lower() for b in blacklist)
            and re.fullmatch(r"[A-Za-z.\s]+", line)
        ):
            name = line.title()
            break

    # ---------------- EMAIL ----------------
    email_match = re.search(
        r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
        text
    )
    email = email_match.group() if email_match else "Email not found"

    # ---------------- PHONE ----------------
    phone_match = re.search(
        r"(\+?\d{1,3}[\s\-]?)?\d{10}",
        text.replace(" ", "")
    )
    phone = phone_match.group() if phone_match else "Phone not found"

    # ---------------- LINKS (SAFE EXTRACTION) ----------------
    linkedin = "LinkedIn not found"
    github = "GitHub not found"
    portfolio = "Portfolio not found"

    url_pattern = re.compile(r"https?://[^\s]+")

    blacklist_domains = {
        "gmail.com", "yahoo.com", "outlook.com",
        "linkedin.com", "github.com",
        "facebook.com", "instagram.com", "twitter.com"
    }

    portfolio_platforms = {
        "netlify.app", "vercel.app", "github.io",
        "pages.dev", "web.app", "firebaseapp.com",
        "render.com", "herokuapp.com"
    }

    for match in url_pattern.finditer(text):
        url = match.group().strip(".,)")
        clean = url.lower()

        if "linkedin.com/in/" in clean:
            linkedin = url

        elif "github.com/" in clean and not clean.endswith("github.com"):
            github = url

        elif not any(b in clean for b in blacklist_domains):
            # Accept hosting platforms or custom domain (example.com)
            if any(p in clean for p in portfolio_platforms) or clean.count(".") == 1:
                portfolio = url

    return {
        "name": name,
        "email": email,
        "phone": phone,
        "linkedin": linkedin,
        "github": github,
        "portfolio": portfolio
    }

# --------------------------------------------------
# ATS SCORE
# --------------------------------------------------
def ats_score(resume, jd):
    resume_words = set(re.findall(r"\b[a-zA-Z]{3,}\b", resume.lower()))
    jd_words = set(re.findall(r"\b[a-zA-Z]{3,}\b", jd.lower()))
    match_ratio = len(resume_words & jd_words) / max(1, len(jd_words))
    return round(min(98, 35 + match_ratio * 65))

# --------------------------------------------------
# REAL ATS SKILL ENGINE
# --------------------------------------------------

STOPWORDS = {
    "and","or","are","is","with","any","basic","clean","good",
    "strong","knowledge","skills","experience","using","able",
    "work","job","role","developer","development","develop",
    "responsible","looking","applications","application",
    "code","coding","issue","issues","efficient","framework",
    "software","system","systems","tools","technology"
}
SKILL_LIBRARY = {
    # Programming
    "python","java","c","c++","c#","sql","r",

    # Web
    "html","css","javascript","bootstrap",
    "react","node","express",
    "flask","django","streamlit",

    # Databases
    "mysql","postgresql","mongodb","sqlite","sql",

    # Data / AI
    "data analysis","data analytics","machine learning",
    "deep learning","nlp","computer vision","data science",
    "pandas","numpy","matplotlib","seaborn",

    # Tools
    "git","github","docker","linux",
    "api","rest api","json",

    # BI / Cloud
    "power bi","tableau",
    "aws","azure","gcp"
}



def skill_gap(resume, jd):
    resume = resume.lower()
    jd = jd.lower()

    matched, missing = set(), set()

    # multi-word skills
    for skill in SKILL_LIBRARY:
        if " " in skill:
            if skill in resume and skill in jd:
                matched.add(skill)
            elif skill in jd and skill not in resume:
                missing.add(skill)

    resume_words = {
        w for w in re.findall(r"\b[a-zA-Z]{3,}\b", resume)
        if w not in STOPWORDS
    }
    jd_words = {
        w for w in re.findall(r"\b[a-zA-Z]{3,}\b", jd)
        if w not in STOPWORDS
    }

    for skill in SKILL_LIBRARY:
        if " " not in skill:
            if skill in resume_words and skill in jd_words:
                matched.add(skill)
            elif skill in jd_words and skill not in resume_words:
                missing.add(skill)

    return sorted(matched)[:10], sorted(missing)[:10]

# --------------------------------------------------
# 🔥 REAL-TIME ANALYSIS HELPERS
# --------------------------------------------------
def skill_usage_depth(resume, skills):
    depth = {}
    for s in skills:
        depth[s] = resume.lower().count(s)
    return depth

def has_metrics(resume):
    return bool(re.search(r"\b\d+%|\b\d+\s?(accuracy|users|records|increase|reduction)", resume.lower()))

def jd_phrase_gap(resume, jd):
    jd_words = set(re.findall(r"\b[a-zA-Z]{5,}\b", jd.lower()))
    resume_words = set(re.findall(r"\b[a-zA-Z]{5,}\b", resume.lower()))
    return list(jd_words - resume_words)[:5]

# --------------------------------------------------
# ✅ REAL-TIME SUGGESTION ENGINE
# --------------------------------------------------
def generate_resume_suggestions(resume, jd, score, matched, missing):
    suggestions = []

    depth = skill_usage_depth(resume, matched)
    metrics = has_metrics(resume)
    jd_missing = jd_phrase_gap(resume, jd)

    for skill, count in depth.items():
        if count == 1:
            suggestions.append(
                f"You mention **{skill}** only once. Recruiters prefer seeing skills reinforced through projects or experience."
            )

    if missing:
        suggestions.append(
            f"The role expects **{missing[0]}**, but it is missing from your resume. "
            f"Adding even a mini-project or coursework can improve ATS ranking."
        )

    if jd_missing:
        suggestions.append(
            f"Important job description terms like **{', '.join(jd_missing[:3])}** are missing. "
            f"ATS systems reward resumes that mirror JD language naturally."
        )

    if not metrics:
        suggestions.append(
            "Your resume lacks measurable impact. Add metrics like accuracy %, performance improvement, or user count."
        )

    if score < 70:
        suggestions.append(
            "Rewrite your Professional Summary using exact keywords from the job description to improve ATS match."
        )

    if not suggestions:
        suggestions.append(
            "Your resume aligns well with the job description. Minor wording improvements can further strengthen it."
        )

    return suggestions[:5]

# --------------------------------------------------
# 👩‍💼 RECRUITER VIEW ENGINE (NEW FEATURE)
# --------------------------------------------------
def recruiter_analysis(resume, matched_skills, missing_skills, score):

    strengths = []
    risks = []

    resume_lower = resume.lower()

    # ---------- STRENGTHS ----------
    if len(matched_skills) >= 5:
        strengths.append("Strong alignment with job technical requirements")

    if "python" in matched_skills:
        strengths.append("Python development capability detected")

    if any(db in matched_skills for db in ["mysql", "postgresql", "mongodb"]):
        strengths.append("Database knowledge present")

    if re.search(r"\b\d+%|\b\d+\s?(users|accuracy|increase|reduction)", resume_lower):
        strengths.append("Quantified achievements improve recruiter confidence")

    if score >= 80:
        strengths.append("High ATS compatibility")

    # ---------- RISK FLAGS ----------
    if len(missing_skills) >= 5:
        risks.append("Multiple required skills missing")

    if "git" in missing_skills:
        risks.append("Version control experience not visible")

    if not re.search(r"(team|collaborated|communication)", resume_lower):
        risks.append("Soft skills not clearly demonstrated")

    if score < 65:
        risks.append("Low ATS alignment may reduce shortlist chances")

    # ---------- HIRING CONFIDENCE ----------
    confidence = min(
        95,
        int(score * 0.7 + len(matched_skills) * 3)
    )

    return strengths, risks, confidence

# --------------------------------------------------
# 🤖 AI RECRUITER CONFIDENCE ENGINE
# --------------------------------------------------
@st.cache_data(show_spinner=False)
def ai_recruiter_confidence(resume, matched, missing, score):

    resume_lower = resume.lower()
    confidence = 40

    # skill impact
    confidence += len(matched) * 4
    confidence -= len(missing) * 2

    # project depth
    project_words = [
        "developed","built","implemented",
        "designed","trained","created","integrated"
    ]

    project_strength = sum(resume_lower.count(w) for w in project_words)
    confidence += min(project_strength * 2, 15)

    # metrics detection
    if re.search(r"\d+%|\d+\s?(users|accuracy|increase|reduction)", resume_lower):
        confidence += 10

    # experience signal
    if re.search(r"(intern|experience|worked|company)", resume_lower):
        confidence += 8

    # ATS weight
    confidence += int(score * 0.25)

    # short resume penalty
    if len(resume.split()) < 250:
        confidence -= 8

    confidence = max(25, min(96, confidence))
    return confidence


# --------------------------------------------------
# 🧠 RECRUITER FINAL DECISION
# --------------------------------------------------
def recruiter_decision(confidence):

    if confidence >= 80:
        return "✅ Strong Hire", "success"
    elif confidence >= 60:
        return "⚠️ Consider", "warning"
    else:
        return "❌ Reject", "error"

# --------------------------------------------------
# AI PROFILE SUMMARY
# --------------------------------------------------
def generate_ai_profile_summary(details, matched_skills, jd_text):
    
    # Extract top important JD keywords
    jd_keywords = re.findall(r"\b[A-Za-z]{5,}\b", jd_text.lower())
    jd_keywords = list(dict.fromkeys(jd_keywords))[:6]

    skills = ", ".join(matched_skills[:5]) if matched_skills else "relevant technologies"
    jd_part = ", ".join(jd_keywords[:4]) if jd_keywords else "modern development practices"

    summary = (
        f"Motivated and detail-oriented software graduate with hands-on experience in {skills}. "
        f"Strong understanding of {jd_part}. "
        f"Proven ability to develop scalable applications and solve real-world problems efficiently. "
        f"Eager to contribute technical expertise in a dynamic organization while continuously enhancing skills."
    )

    return summary


# --------------------------------------------------
# EDUCATION (🔥 FIXED PURSUING SUPPORT)
# --------------------------------------------------
def extract_education_section(text):

    block = extract_section(text, "EDUCATION")
    if not block:
        return []

    lines = [l.strip() for l in block.split("\n") if l.strip()]

    entries = []
    current = None

    for line in lines:

        if re.search(r"(mca|bca|b\.?tech|bachelor|master|degree)", line, re.IGNORECASE):

            if current:
                entries.append(current)

            year_match = re.search(r"(20\d{2}\s*[-–]\s*(20\d{2}|Present))", line)

            pursuing = " (Pursuing)" if "present" in line.lower() or "pursuing" in line.lower() else ""

            current = {
                "degree": re.sub(r"\(.*?\)", "", line).strip(),
                "year": year_match.group(0) if year_match else "",
                "institution": "",
                "cgpa": "",
                "pursuing": pursuing
            }

        elif re.search(r"(college|university|school|institute)", line, re.IGNORECASE):
            if current:
                current["institution"] = line

        elif "cgpa" in line.lower():
            if current:
                current["cgpa"] = line

    if current:
        entries.append(current)

    return entries

# --------------------------------------------------
# INTERNSHIP EXTRACTION (ATS UNIVERSAL VERSION)
# --------------------------------------------------
def extract_internship_section(text):

    if not text:
        return []

    section_names = [
        "INTERNSHIP EXPERIENCE",
        "INTERNSHIPS",
        "INTERNSHIP",
        "EXPERIENCE",
        "WORK EXPERIENCE"
    ]

    block = ""
    for name in section_names:
        block = extract_section(text, name)
        if block:
            break

    if not block:
        return []

    lines = [l.strip() for l in block.split("\n") if l.strip()]

    internships = []
    current = None
    description = []

    STOP_HEADERS = (
        "project",
        "education",
        "skill",
        "technical",
        "certification",
        "summary"
    )

    for line in lines:

        lower = line.lower()

        # ✅ STOP safely when next section begins
        if any(lower.startswith(h) for h in STOP_HEADERS):
            break

        # ---- DURATION ----
        duration_match = re.search(
            r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s*\d{4}.*?(present|\d{4})?",
            lower
        )

        if duration_match and current:
            current["duration"] = line
            continue

        # ---- BULLETS ----
        if line.startswith(("•", "-", "–")):
            if current:
                description.append(line.lstrip("•-– ").strip())
            continue

        # ---- NEW TITLE ----
        if len(line.split()) <= 12:

            if current:
                current["description"] = " ".join(description)
                internships.append(current)

            current = {
                "title": line,
                "duration": "",
                "description": ""
            }
            description = []
            continue

        # ---- DESCRIPTION ----
        if current:
            description.append(line)

    if current:
        current["description"] = " ".join(description)
        internships.append(current)

    return internships

# --------------------------------------------------
# ✅ UNIVERSAL EXPERIENCE EXTRACTOR (ATS STYLE)
# --------------------------------------------------
def extract_experience_section(text):

    if not text:
        return []

    experience_headers = [
        "EXPERIENCE",
        "WORK EXPERIENCE",
        "PROFESSIONAL EXPERIENCE",
        "TRAINING",
        "INDUSTRIAL TRAINING"
    ]

    header_pattern = "|".join(experience_headers)

    match = re.search(
        rf"({header_pattern})\s*\n(.*?)(?=\n[A-Z ]{{4,}}\n|\Z)",
        text,
        re.IGNORECASE | re.DOTALL
    )

    if not match:
        return []

    block = match.group(2)

    lines = [l.strip() for l in block.split("\n") if l.strip()]

    experiences = []
    current = None
    description = []

    for line in lines:

        # NEW ENTRY (company/title line)
        if len(line.split()) <= 12 and not line.startswith(("•", "-", "–")):

            if current:
                current["description"] = " ".join(description)
                experiences.append(current)

            current = {
                "title": line,
                "duration": "",
                "description": ""
            }
            description = []
            continue

        # duration detection
        if re.search(r"(20\d{2}|present|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)",
                     line.lower()):
            if current and not current["duration"]:
                current["duration"] = line
                continue

        # description
        clean = line.lstrip("•-– ").strip()
        description.append(clean)

    if current:
        current["description"] = " ".join(description)
        experiences.append(current)

    return experiences

# --------------------------------------------------
# PROJECTS (🔥 FIXED)
# --------------------------------------------------
def extract_project_section(text):

    if not text:
        return []

    block = extract_section(text, "PROJECTS")

    if not block:
        block = extract_section(text, "ACADEMIC PROJECTS")

    if not block:
        return []

    lines = [l.strip() for l in block.split("\n") if l.strip()]

    projects = []
    current = None
    description = []

    # verbs normally used in descriptions
    description_verbs = (
        "developed", "created", "implemented",
        "designed", "built", "used", "applied",
        "integrated", "trained", "analyzed"
    )

    STOP_HEADERS = (
        "technical",
        "technical skills",
        "skills",
        "education",
        "certifications",
        "internship",
        "experience"
    )

    for line in lines:

        clean = line.strip()
        lower = clean.lower()

        # ✅ STOP when next section starts
        if any(lower.startswith(h) for h in STOP_HEADERS):
            break

        # ✅ TECHNOLOGY LINE
        if "technolog" in lower:
            if current:
                current["technologies"] = clean
            continue

        # ✅ BULLET DESCRIPTION
        if clean.startswith(("•", "-", "–")):
            if current:
                description.append(clean.lstrip("•-– ").strip())
            continue

        # ✅ TITLE DETECTION (SMART)
        is_title = (
            not lower.startswith(description_verbs)   # NOT sentence
            and len(clean.split()) <= 12              # short
        )

        if is_title:
            if current:
                current["description"] = " ".join(description)
                projects.append(current)

            current = {
                "title": clean,
                "description": "",
                "technologies": ""
            }
            description = []
            continue

        # ✅ NORMAL DESCRIPTION
        if current:
            description.append(clean)

    if current:
        current["description"] = " ".join(description)
        projects.append(current)

    return projects

# --------------------------------------------------
# ✅ EXPERIENCE VALIDATOR (REAL ATS LOGIC)
# --------------------------------------------------
def is_real_experience(exp):

    text = (
        exp.get("title","") + " " +
        exp.get("duration","") + " " +
        exp.get("description","")
    ).lower()

    # must contain date or duration
    has_date = bool(re.search(
        r"(20\d{2}|present|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)",
        text
    ))

    # must look like company/role
    role_keywords = [
        "engineer","developer","analyst","consultant",
        "company","solutions","technologies","pvt","ltd"
    ]

    has_role = any(word in text for word in role_keywords)

    # must contain work action verbs
    work_words = [
        "developed","built","designed","implemented",
        "worked","created","maintained","handled"
    ]

    has_work = any(word in text for word in work_words)

    return has_date and has_role and has_work


# --------------------------------------------------
# ✅ CHECK IF CANDIDATE IS EXPERIENCED
# --------------------------------------------------
def is_candidate_experienced(experience_list):

    real_exp = [
        exp for exp in experience_list
        if is_real_experience(exp)
    ]

    return len(real_exp) > 0


# --------------------------------------------------
# PDF GENERATION 
# --------------------------------------------------
def generate_optimized_resume_pdf(details, matched, missing, resume, jd):
    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40
    )

    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(
        name="Name",
        fontSize=20,
        spaceAfter=8,
        alignment=TA_LEFT,
        leading=24,
        fontName="Helvetica-Bold"   # 👈 makes it bold
    ))
  
    styles.add(ParagraphStyle(
        name="Section",
        fontSize=12,
        spaceBefore=14,
        spaceAfter=6,
        leading=14,
        fontName="Helvetica-Bold"
    ))

    styles.add(ParagraphStyle(
        name="Body",
        fontSize=10,
        leading=14,
        spaceAfter=6
    ))

    content = []

    # ---------- HEADER ----------
    content.append(Paragraph(details["name"].upper(), styles["Name"]))

    linkedin_display = details['linkedin'].replace("https://","").replace("http://","")
    github_display = details['github'].replace("https://","").replace("http://","")

    # ---------- CLICKABLE LINKS ----------
    def make_clickable(url):
        if url and "not found" not in url.lower():
            return f'<link href="{url}" color="blue">{url.replace("https://","").replace("http://","")}</link>'
        return ""

    linkedin_link = make_clickable(details["linkedin"])
    github_link = make_clickable(details["github"])
    portfolio_link = make_clickable(details["portfolio"])

    contact_line = f"""
    {details['email']} | {details['phone']}<br/>
    LinkedIn: {linkedin_link}<br/>
    GitHub: {github_link}<br/>
    Portfolio: {portfolio_link}
    """

    content.append(Paragraph(contact_line, styles["Body"]))


    from reportlab.platypus import Spacer
    content.append(Spacer(1, 10))


    # ---------- SUMMARY ----------
    content.append(Paragraph("PROFESSIONAL SUMMARY", styles["Section"]))
    content.append(Paragraph(
        generate_ai_profile_summary(details, matched, st.session_state.jd),
        styles["Body"]
    ))
    
    #---------- EDUCATION ---------
    education_data = extract_education_section(resume)

    if education_data:
        content.append(Paragraph("EDUCATION", styles["Section"]))

        for edu in education_data:

            degree_line = f"<b>{edu['degree']}</b>"

            if edu['year']:
                degree_line += f" ({edu['year']})"

            if edu.get('pursuing', False) and "pursuing" not in degree_line.lower():
                degree_line += edu['pursuing']

            content.append(Paragraph(degree_line, styles["Body"]))

            if edu['institution']:
                content.append(Paragraph(edu['institution'], styles["Body"]))

            if edu['cgpa']:
                content.append(Paragraph(edu['cgpa'], styles["Body"]))

            content.append(Spacer(1,8))

    # ---------- INTERNSHIP ----------
    internship_data = extract_internship_section(resume)

    if internship_data:
        content.append(Paragraph("INTERNSHIP EXPERIENCE", styles["Section"]))

        for intern in internship_data:

            # ✅ TITLE (always show)
            if intern.get("title"):
                content.append(
                    Paragraph(f"<b>{intern['title']}</b>", styles["Body"])
                )

            # ✅ DURATION (show only if exists)
            if intern.get("duration"):
                content.append(
                    Paragraph(intern["duration"], styles["Body"])
                )

            # ✅ DESCRIPTION (safe check)
            if intern.get("description"):
                content.append(
                    Paragraph(intern["description"], styles["Body"])
                )

            content.append(Spacer(1, 8))
            
    # ---------- EXPERIENCE (SMART ATS FILTER) ----------
    experience_data = extract_experience_section(resume)

    # show only if REAL job experience exists
    if experience_data and is_candidate_experienced(experience_data):

        content.append(Paragraph("EXPERIENCE", styles["Section"]))

        for exp in experience_data:

            # skip fake or internship-like entries
            if not is_real_experience(exp):
                continue

            if exp.get("title"):
                content.append(
                    Paragraph(f"<b>{exp['title']}</b>", styles["Body"])
                )

            if exp.get("duration"):
                content.append(
                    Paragraph(exp["duration"], styles["Body"])
                )

            if exp.get("description"):
                content.append(
                    Paragraph(exp["description"], styles["Body"])
                )

            content.append(Spacer(1,8))
             
    # ---------- PROJECTS ----------
    project_data = extract_project_section(resume)

    if project_data:
        content.append(Paragraph("PROJECTS", styles["Section"]))

        for project in project_data:

            content.append(
                Paragraph(f"<b>{project['title']}</b>", styles["Body"])
            )

            if project['description']:
                content.append(
                    Paragraph(project['description'], styles["Body"])
            )

            if project['technologies']:
                content.append(
                    Paragraph(project['technologies'], styles["Body"])
                )

            content.append(Spacer(1,8))
 
    # ---------- CORE SKILLS ----------
    content.append(Paragraph("CORE SKILLS", styles["Section"]))

    if matched:
        skill_lines = [
            f"• Programming: {', '.join([s for s in matched if s in ['python','javascript','java']])}",
            f"• Web: {', '.join([s for s in matched if s in ['html','css','flask','django']])}",
            f"• Databases: {', '.join([s for s in matched if s in ['mysql','postgresql']])}",
            f"• Tools: {', '.join([s for s in matched if s in ['git','github','docker']])}",
        ]
        for line in skill_lines:
            if ":" in line and line.split(":")[1].strip():
                content.append(Paragraph(line, styles["Body"]))
    else:
        content.append(Paragraph("Python, SQL, Git", styles["Body"]))
        
    # ---------- BUILD PDF (FINAL STEP) ----------
    try:
        doc.build(content)

        pdf_bytes = buffer.getvalue()   # ✅ convert to bytes
        buffer.close()

        return pdf_bytes

    except Exception as e:
        print("PDF ERROR:", e)
        return None


# =================================================
# CSS
# =================================================
st.markdown("""
<style>
body { background-color:#f4f7fb; }

.app-header {
    background: linear-gradient(135deg,#4f46e5,#9333ea);
    padding: 1.5rem;
    border-radius: 14px;
    color: white;
    text-align: center;
    margin-bottom: 1rem;
}

.card {
    background: white;
    padding: 1.2rem;
    border-radius: 14px;
    box-shadow: 0 4px 18px rgba(0,0,0,0.08);
}
/* Reserve space so footer doesn't overlap */
.stApp {
    padding-bottom: 60px;
}

/* Footer bar */
.custom-footer {
    position: fixed;
    bottom: 0;
    left: 0;
    width: 100%;
    height: 52px;
    background: linear-gradient(90deg, #050a1f, #0a1a3f);
    color: white;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 36px;
    font-size: 14px;
    z-index: 1000;
    box-shadow: 0 -2px 8px rgba(0,0,0,0.35);
}

/* Links */
.custom-footer a {
    color: #38bdf8;
    text-decoration: none;
    margin-left: 18px;
    font-weight: 500;
}

.custom-footer a:hover {
    text-decoration: underline;
}
</style>
""", unsafe_allow_html=True)

# =================================================
# HEADER
# =================================================
st.markdown("""
<div class="app-header">
  <h1>🎯 AI Resume Screening System</h1>
  <p>ATS Score • Skill Gap • Optimized Resume</p>
</div>
""", unsafe_allow_html=True)

# --------------------------------------------------
# LAYOUT
# --------------------------------------------------
left, right = st.columns(2)

# ==================================================
# LEFT SIDE – INPUTS
# ==================================================
with left:
    resume_file = st.file_uploader(
        "📄 Upload Resume (PDF / DOCX)",
        ["pdf", "docx"],
        key=f"resume_uploader_{st.session_state.form_version}"
    )
    resume_text = st.text_area(
        "Or paste resume text",
        height=140,
        key=f"resume_text_{st.session_state.form_version}"
    )

    jd_text = st.text_area(
        "📌 Paste Job Description",
        height=180,
        key=f"jd_text_{st.session_state.form_version}"
    )

    if st.button("🔍 Analyze Resume", disabled=st.session_state.analyzed):
        if not resume_file and not resume_text.strip():
            st.error("Upload or paste resume")
        elif not jd_text.strip():
            st.error("Paste Job Description")
        else:
            if resume_file:
                if resume_file.name.endswith(".pdf"):
                    resume_text = extract_text_from_pdf(resume_file)
                else:
                    resume_text = extract_text_from_docx(resume_file)

            # CLEAN BEFORE SAVING
            cleaned_resume = clean_resume_text(resume_text)

            st.session_state.resume = cleaned_resume
            st.session_state.jd = jd_text
            st.session_state.analyzed = True

# =========================
# RIGHT PANEL
# =========================
with right:

    # ------------------ NOT ANALYZED STATE ------------------
    if not st.session_state.analyzed:
        st.subheader("📊 ATS Results")
        st.info("Upload resume and click **Analyze Resume**")

    # ------------------ ANALYZED STATE ------------------
    else:
        resume = st.session_state.resume
        jd = st.session_state.jd      

        details = extract_user_details(resume)
        score = ats_score(resume, jd)
        matched, missing = skill_gap(resume, jd)

        # ---------- HEADER + RESET BUTTON ----------
        col_title, col_reset = st.columns([5, 1])

        with col_title:
            st.subheader("📊 ATS Results")

        with col_reset:
            if st.button("🔄 Reset"):
                st.session_state.confirm_reset = True

        # ---------- RESET CONFIRMATION (TOAST) ----------
        if st.session_state.get("confirm_reset", False):

            st.toast("⚠️ Confirm reset to analyze another resume", icon="⚠️")

            col_yes, col_no = st.columns([1, 1])

            with col_yes:
                if st.button("✅ Yes, Reset", use_container_width=True):

                    st.toast("♻️ Reset completed", icon="✅")

                    # SAFE RESET (ONLY REQUIRED KEYS)
                    st.session_state.analyzed = False
                    st.session_state.resume = None
                    st.session_state.jd = None
                    st.session_state.pdf_bytes = None
                    st.session_state.confirm_reset = False

                    # reset widgets
                    st.session_state.form_version += 1

                    st.rerun()

            with col_no:
                if st.button("❌ Cancel", use_container_width=True):
                    st.toast("❎ Reset cancelled", icon="❎")
                    st.session_state.confirm_reset = False

        # ---------- RESULTS ----------
        st.success("✅ Resume analyzed successfully!")
        st.metric("ATS Match Score [⭐⭐⭐⭐⭐]", f"{score}%")
        
        st.session_state.recruiter_mode = st.toggle(
            "👩‍💼 Recruiter View Mode",
            value=st.session_state.recruiter_mode,
            key="recruiter_toggle"
        )
        
        # --------------------------------------------------
        # 👩‍💼 RECRUITER VIEW PANEL
        # --------------------------------------------------
        if st.session_state.get("recruiter_mode", False):

            st.markdown("---")
            st.subheader("👩‍💼 Recruiter Insights")

            try:
                strengths, risks, _ = recruiter_analysis(
                    resume, matched, missing, score
                )
                
                confidence = ai_recruiter_confidence(
                    resume,
                    matched,
                    missing,
                    score
                )
                
                col1, col2 = st.columns(2)

                # ✅ Strengths
                with col1:
                    st.markdown("### ✅ Top Strengths")
                    if strengths:
                        for s in strengths:
                            st.success(s)
                    else:
                        st.info("No major strengths detected")

                # ⚠️ Risks
                with col2:
                    st.markdown("### ⚠️ Risk Flags")
                    if risks:
                        for r in risks:
                            st.error(r)
                    else:
                        st.success("No hiring risks detected")

                # 📊 Confidence
                st.markdown("### 🔥 Hiring Confidence")

                confidence = int(confidence)  # ensure integer
                st.progress(confidence / 100)  # progress expects 0–1
                st.metric("Recruiter Confidence Score", f"{confidence}%")

                # --------------------------------------------------
                # 🧠 RECRUITER FINAL DECISION
                # --------------------------------------------------
                decision, decision_type = recruiter_decision(confidence)

                st.markdown("### 🧠 Recruiter Decision")

                if decision_type == "success":
                    st.success(decision)
                elif decision_type == "warning":
                    st.warning(decision)
                else:
                    st.error(decision)

            except Exception as e:
                st.error(f"Recruiter view error: {e}")
          
        #----------- ATS SKILL TO ADD ------------
        st.subheader("🚀 Skills To Add (ATS Gap)")

        if missing:
            for skill in missing:
                st.write("•", skill.title())
        else:
            st.success("No critical skill gaps detected ✅")


        # ---------- SKILL GAP CHART ----------
        fig = go.Figure()

        fig.add_bar(
            x=[len(matched)],
            y=["Matched Skills"],
            orientation="h",
            name="Matched",
            marker_color="#2563eb"
        )

        fig.add_bar(
            x=[len(missing)],
            y=["Missing Skills"],
            orientation="h",
            name="Missing",
            marker_color="#93c5fd"
        )

        fig.update_layout(
            height=320,
            margin=dict(l=80, r=40, t=40, b=40),
            xaxis_title="Skill Count",
            barmode="group",
            legend=dict(orientation="h", y=-0.25, x=0.3)
        )

        st.plotly_chart(fig, use_container_width=True)

        # ---------- IMPROVEMENT SUGGESTIONS ----------
        st.subheader("📝 Resume Improvement Suggestions")
        for s in generate_resume_suggestions(resume, jd, score, matched, missing):
            st.warning("• " + s)
    
        # ---------- PDF DOWNLOAD ----------
        if "pdf_bytes" not in st.session_state:
            st.session_state.pdf_bytes = generate_optimized_resume_pdf(
                details,matched,missing, resume, jd
            ) 
        pdf_bytes = st.session_state.pdf_bytes    

        if pdf_bytes:
            st.download_button(
                "⬇️ Download ATS Optimized Resume (PDF)",
                data=pdf_bytes,
                file_name="ATS_Optimized_Resume.pdf",
                mime="application/pdf"
            )
        else:
            st.error("PDF generation failed.")

         
# --------------------------------------------------
# ✅ FOOTER (FINAL FIX)
# --------------------------------------------------
st.markdown("""
<div class="custom-footer">
    <div>© Hemadharshini • AI Developer</div>
    <div>
        <a href="https://github.com/hemaxplore" target="_blank">GitHub</a>
        <a href="https://www.linkedin.com/in/hemadharshini21/" target="_blank">LinkedIn</a>
        <a href="mailto:darshinihema2102@gmail.com">Email</a>
    </div>
</div>
""", unsafe_allow_html=True)




