"""
Offline sentiment analysis using VADER — no API key or cost required.
VADER is purpose-built for social media / forum text (exactly what Reddit is).

Provides:
  - Sentiment label + score (-1 to 1)
  - Theme detection via keyword matching
  - Citation detection via heuristics
  - Summary (first 2 sentences)
"""

import json
import re
from datetime import datetime, timezone

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from database import get_unanalyzed, save_sentiment, total_unanalyzed, migrate_db, get_conn

_analyzer = SentimentIntensityAnalyzer()

# ── Theme keyword map ─────────────────────────────────────────────────────────
THEME_KEYWORDS = {
    "accreditation": [
        "accredited", "accreditation", "regionally", "nationally", "deac",
        "hlc", "recognized", "legitimate", "legit", "diploma mill",
    ],
    "cost/value": [
        "cost", "tuition", "affordable", "cheap", "expensive", "price",
        "money", "worth", "value", "fee", "pay", "paid", "budget",
    ],
    "flexibility": [
        "flexible", "self-paced", "self paced", "own pace", "schedule",
        "balance", "freedom", "convenience", "work full time", "part time",
    ],
    "job outcomes": [
        "job", "career", "hired", "hiring", "salary", "promotion",
        "employed", "employment", "work", "industry", "field",
    ],
    "student support": [
        "support", "advisor", "mentor", "mentors", "guidance", "help",
        "counselor", "resources", "responsive", "communicate",
    ],
    "program quality": [
        "program", "curriculum", "course", "courses", "quality",
        "rigorous", "challenging", "content", "material", "learn",
    ],
    "reputation": [
        "reputation", "respected", "diploma mill", "prestige", "name",
        "brand", "known", "perception", "stigma", "opinion",
    ],
    "financial aid": [
        "financial aid", "fafsa", "loan", "loans", "grant", "grants",
        "scholarship", "funding", "aid",
    ],
    "technology": [
        "platform", "portal", "website", "app", "system", "online",
        "interface", "technology", "tech", "tools",
    ],
    "workload": [
        "workload", "difficult", "easy", "hard", "challenging", "time",
        "busy", "stress", "overwhelming", "manageable",
    ],
    "graduation": [
        "graduated", "graduate", "degree", "completed", "finish",
        "done", "diploma", "certificate",
    ],
    "transfer credits": [
        "transfer", "credits", "prior learning", "previous", "accepted",
        "credit hours",
    ],
    "employer acceptance": [
        "employer", "hiring manager", "resume", "interview",
        "background check", "hr", "recruiter",
    ],
}

# ── Program keyword map ───────────────────────────────────────────────────────
PROGRAM_KEYWORDS = {
    "Cybersecurity": [
        "cybersecurity", "cyber security", "information security", "infosec",
        "cissp", "security+", "network security", "ethical hacking", "penetration",
    ],
    "IT / Networking": [
        "information technology", "it degree", "it program", "network administration",
        "networking", "comptia", "network+", "a+ cert", "helpdesk", "help desk",
        "sysadmin", "systems admin",
    ],
    "Computer Science": [
        "computer science", "cs degree", "cs program", "software engineering",
        "software development", "programming", "coding degree", "developer degree",
    ],
    "Cloud / DevOps": [
        "cloud computing", "aws", "azure", "google cloud", "devops",
        "cloud cert", "solutions architect",
    ],
    "Data Science / Analytics": [
        "data science", "data analytics", "data analysis", "machine learning",
        "artificial intelligence", "ai degree", "business analytics",
    ],
    "Nursing": [
        "nursing", "rn to bsn", "bsn", "msn", "registered nurse", "rn program",
        "nurse practitioner", "np program", "pre-licensure", "nclex",
    ],
    "Healthcare Management": [
        "healthcare management", "health administration", "healthcare admin",
        "mha", "health informatics", "public health",
    ],
    "MBA": [
        "mba", "master of business administration", "masters in business",
        "executive mba",
    ],
    "Business": [
        "business degree", "business administration", "bba", "business management",
        "business program", "entrepreneurship",
    ],
    "Accounting / Finance": [
        "accounting", "cpa", "bookkeeping", "finance degree", "financial management",
        "tax", "audit",
    ],
    "Marketing": [
        "marketing degree", "digital marketing", "marketing program",
        "marketing management",
    ],
    "Human Resources": [
        "human resources", "hr degree", "hrm", "hr management",
        "talent management", "shrm",
    ],
    "Project Management": [
        "project management", "pmp", "scrum master", "agile", "capm",
    ],
    "Supply Chain": [
        "supply chain", "logistics", "operations management", "procurement",
    ],
    "Education / Teaching": [
        "education degree", "teaching degree", "teacher licensure", "k-12",
        "special education", "curriculum", "instructional design", "master of education",
        "med degree",
    ],
    "Psychology / Counseling": [
        "psychology", "counseling", "mental health degree", "behavioral health",
        "social work",
    ],
    "Criminal Justice": [
        "criminal justice", "criminology", "law enforcement degree",
        "homeland security",
    ],
}


def _detect_programs(text: str) -> list:
    text_lower = text.lower()
    found = []
    for program, keywords in PROGRAM_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            found.append(program)
    return found


# ── Citation heuristics ───────────────────────────────────────────────────────
CITATION_PATTERNS = [
    r"\bvs\.?\b", r"\bversus\b", r"\bcompared? to\b", r"\bor (wgu|snhu|gcu|purdue|phoenix)\b",
    r"\brecommend\b", r"\bsuggests?\b", r"\bgo with\b", r"\bchoose\b",
    r"\bpick\b", r"\bbetter than\b", r"\bworse than\b",
    r"\bavoid\b", r"\bstay away\b", r"\bwarning\b", r"\bdon'?t go\b",
    r"\bswitch(ed|ing)?\b", r"\btransferred? (to|from)\b",
    r"\bconsidering\b", r"\bdeciding\b", r"\bwhich (school|university|college)\b",
    r"\bshould i (go|attend|enroll|choose)\b",
]
_CITATION_RE = re.compile("|".join(CITATION_PATTERNS), re.IGNORECASE)


def _detect_themes(text: str) -> list:
    text_lower = text.lower()
    found = []
    for theme, keywords in THEME_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            found.append(theme)
    return found[:5]


def _is_citation(text: str) -> bool:
    return bool(_CITATION_RE.search(text))


def _summarize(text: str) -> str:
    """Return the first 1-2 sentences, capped at 200 chars."""
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    summary = " ".join(sentences[:2])
    return summary[:200] + ("…" if len(summary) > 200 else "")


def _label(compound: float) -> str:
    if compound >= 0.05:
        return "positive"
    if compound <= -0.05:
        return "negative"
    return "neutral"


def _analyze_one(mention: dict) -> dict:
    text = (mention.get("body") or "").strip()
    if not text:
        return None

    scores = _analyzer.polarity_scores(text)
    compound = scores["compound"]

    # Promote to "mixed" when both pos and neg are significant
    label = _label(compound)
    if scores["pos"] > 0.15 and scores["neg"] > 0.15:
        label = "mixed"

    return {
        "mention_id": mention["id"],
        "sentiment": label,
        "score": round(compound, 4),
        "themes": json.dumps(_detect_themes(text)),
        "programs": json.dumps(_detect_programs(text)),
        "is_citation": 1 if _is_citation(text) else 0,
        "summary": _summarize(text),
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
    }


def backfill_programs() -> int:
    """Tag programs on already-analyzed mentions that don't have program data yet."""
    conn = get_conn()
    rows = conn.execute("""
        SELECT m.id, m.body FROM mentions m
        INNER JOIN sentiment s ON m.id = s.mention_id
        WHERE s.programs IS NULL AND m.body IS NOT NULL AND length(trim(m.body)) > 20
    """).fetchall()
    conn.close()

    if not rows:
        return 0

    print(f"  Backfilling programs for {len(rows)} mentions...")
    count = 0
    conn = get_conn()
    for row in rows:
        programs = _detect_programs(row["body"] or "")
        conn.execute(
            "UPDATE sentiment SET programs=? WHERE mention_id=?",
            (json.dumps(programs), row["id"])
        )
        count += 1
    conn.commit()
    conn.close()
    print(f"  ✓ {count} mentions tagged with programs")
    return count


def run(batch_size: int = 200) -> int:
    migrate_db()
    backfill_programs()

    pending = total_unanalyzed()
    if pending == 0:
        print("  Nothing new to analyze.")
        return 0

    print(f"  {pending} mentions to analyze (offline, no API needed)...")
    total = 0

    while True:
        batch = get_unanalyzed(batch_size)
        if not batch:
            break
        success = 0
        for mention in batch:
            result = _analyze_one(mention)
            if result:
                save_sentiment(result)
                success += 1
        print(f"  ✓ {success} analyzed")
        total += success

    return total
