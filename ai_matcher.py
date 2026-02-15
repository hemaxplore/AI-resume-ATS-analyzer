from sentence_transformers import SentenceTransformer, util
import re
import streamlit as st

# ================= SAFE MODEL LOADING =================
@st.cache_resource(show_spinner=False)
def load_model():
    return SentenceTransformer("all-MiniLM-L6-v2")

# =====================================================

def clean_text(text):
    return re.sub(r"\s+", " ", text.lower())

def extract_skills_from_jd(jd_text):
    """
    Dynamically extracts skill-like terms from JD
    """
    skill_patterns = [
        "python", "java", "sql", "machine learning", "data science",
        "deep learning", "nlp", "pandas", "numpy", "scikit-learn",
        "power bi", "excel", "statistics", "tensorflow", "pytorch",
        "flask", "django"
    ]

    jd_text = jd_text.lower()
    return [skill for skill in skill_patterns if skill in jd_text]

def semantic_match_score(resume_text, jd_text):
    """
    AI semantic similarity score (0–100)
    """
    model = load_model()   # ✅ cached, no re-download

    resume_emb = model.encode(
        clean_text(resume_text),
        convert_to_tensor=True
    )
    jd_emb = model.encode(
        clean_text(jd_text),
        convert_to_tensor=True
    )

    similarity = util.cos_sim(resume_emb, jd_emb).item()
    return round(similarity * 100, 2)

def skill_gap_analysis(resume_text, jd_text):
    required_skills = extract_skills_from_jd(jd_text)
    resume_text = resume_text.lower()

    matched = [s for s in required_skills if s in resume_text]
    missing = [s for s in required_skills if s not in resume_text]

    return matched, missing

def role_fit_decision(score, missing_skills):
    if score >= 75 and len(missing_skills) <= 1:
        return "🟢 Strong Fit", "Proceed to technical interview"
    elif score >= 50:
        return "🟡 Moderate Fit", "Suitable for trainee / junior role"
    else:
        return "🔴 Low Fit", "Not recommended without upskilling"

def ai_explanation(score, matched, missing):
    return {
        "strengths": (
            "Good semantic alignment with job description"
            if score >= 50 else
            "Limited alignment with job requirements"
        ),
        "weaknesses": (
            "Missing key skills: " + ", ".join(missing)
            if missing else
            "No major skill gaps identified"
        )
    }

def learning_recommendations(missing_skills):
    roadmap = {
        "machine learning": ("Supervised → Unsupervised → Projects", "4–6 weeks"),
        "data science": ("EDA → Statistics → ML", "5–6 weeks"),
        "nlp": ("Text cleaning → TF-IDF → Transformers", "4 weeks"),
        "statistics": ("Probability → Inferential stats", "2–3 weeks"),
        "power bi": ("DAX → Dashboards → Reports", "2–3 weeks"),
        "python": ("Core → Pandas → Projects", "3–4 weeks"),
    }

    recs = {}
    for skill in missing_skills:
        if skill in roadmap:
            recs[skill] = {
                "path": roadmap[skill][0],
                "time": roadmap[skill][1]
            }

    return recs
