"""Score jobs for a profile: keyword pre-filter + salary parse + Jev fit.
Run: python score.py [profile]  (defaults to the only profile if there's just one)"""
import os
import re
import sqlite3
import sys
from pathlib import Path

from config import (JEV_MAX_JOBS, PROFILES_DIR, VOCAB, WEIGHT_SENIORITY,
                    WEIGHT_SKILL, init_db)

USD_TO_MXN = 20.0  # ponytail: fixed rate; bump when it drifts
AMOUNT_RE = re.compile(
    r"\$\s*(\d{1,3}(?:,\d{3})+)(?:\s*(?:-|–|a|al|to)\s*\$?\s*(\d{1,3}(?:,\d{3})+))?")


def derive_keywords(cv_text):
    cv = cv_text.lower()
    return [k for k in VOCAB if k in cv]


def kw_score(title, desc, keywords):
    """Distinct keyword hits; title hits count double."""
    text = f"{title}\n{desc}".lower()
    t = title.lower()
    return sum(1 for k in keywords if k in text) + sum(1 for k in keywords if k in t)


def to_monthly(mid, interval, currency):
    if interval == "yearly":
        mid /= 12
    elif interval == "weekly":
        mid *= 4.33
    elif interval == "hourly":
        mid *= 160
    elif interval is None and mid > 500_000:
        mid /= 12  # no interval + big number: assume yearly
    if (currency or "").upper().startswith("US"):
        mid *= USD_TO_MXN
    return mid


def salary_from_text(desc):
    """First plausible $ amount in the description, assumed monthly MXN.
    ponytail: naive heuristic; upgrade to a Jev extraction question if it misfires often."""
    for m in AMOUNT_RE.finditer(desc):
        lo = float(m.group(1).replace(",", ""))
        hi = float(m.group(2).replace(",", "")) if m.group(2) else None
        mid = (lo + hi) / 2 if hi else lo
        if 5_000 <= mid <= 500_000:
            return mid
    return None


def get_profile(arg):
    profiles = sorted(p.stem for p in Path(PROFILES_DIR).glob("*.txt"))
    if arg:
        return arg
    if len(profiles) == 1:
        return profiles[0]
    sys.exit(f"usage: python score.py <profile> "
             f"(available: {', '.join(profiles) or 'none — upload a CV first'})")


def jev_fit(con, rows, cv, profile):
    """Judge pre-filtered jobs with Jev: one request per job, 4 parallel questions.
    ponytail: sequential requests; switch to AsyncTypeSafeClient if a run feels slow."""
    if not os.environ.get("TYPESAFE_API_KEY"):
        print("TYPESAFE_API_KEY not set; skipping Jev (keyword scores only)")
        return 0
    from typesafe_sdk import Noul, NoulCriteria, Score, TypeSafeClient

    questions = {
        "skill_fit": Score(
            instructions="How well does the candidate's experience and skills match what this job posting requires?",
            criteria=[
                "Different field or stack; the candidate has none of the core requirements",
                "Adjacent field; a few transferable skills but major gaps in the core stack",
                "Partial match; the candidate covers some core requirements",
                "Strong match; the candidate covers most core requirements",
                "Near-perfect match; the candidate covers core and secondary requirements",
            ]),
        "seniority_fit": Score(
            instructions="How well does the seniority level of this role match the candidate's level?",
            criteria=[
                "Completely mismatched level, e.g. an internship or a staff/principal role for a mid-level candidate",
                "Noticeable gap; the candidate is clearly over- or under-qualified",
                "Close; one step above or below the candidate's level",
                "Exactly the candidate's level",
            ]),
        "requires_english": Noul(
            instructions="Does this job posting require the candidate to speak or write English?"),
        "truly_remote": Noul(
            instructions="Is this job fully remote with no required office days?",
            criteria=NoulCriteria(
                true="States fully remote or 100% remote with no mention of office presence",
                false="Mentions hybrid, some office days, or on-site requirements",
            )),
    }

    judged = 0
    with TypeSafeClient() as client:
        for jid, title, company, location, desc in rows:
            state = {
                "candidate_cv": cv,
                "job": {"title": title, "company": company,
                        "location": location, "description": desc[:6000]},
            }
            try:
                r = client.system_one(model="jev-latest", state=state, questions=questions)
                a = r.answers
                skill = a["skill_fit"].score / 4
                seniority = a["seniority_fit"].score / 3
                fit = WEIGHT_SKILL * skill + WEIGHT_SENIORITY * seniority
                con.execute(
                    """INSERT INTO judgments
                       (job_id, profile, jev_skill, jev_seniority, jev_english, jev_remote, fit)
                       VALUES (?,?,?,?,?,?,?)
                       ON CONFLICT(job_id, profile) DO UPDATE SET
                       jev_skill=excluded.jev_skill, jev_seniority=excluded.jev_seniority,
                       jev_english=excluded.jev_english, jev_remote=excluded.jev_remote,
                       fit=excluded.fit""",
                    (jid, profile, skill, seniority, a["requires_english"].noul,
                     a["truly_remote"].noul, fit))
                judged += 1
            except Exception as e:
                print(f"jev failed for job {jid} ({title}): {e}")
    return judged


def main():
    profile = get_profile(sys.argv[1] if len(sys.argv) > 1 else None)
    cv = Path(PROFILES_DIR, f"{profile}.txt").read_text(encoding="utf-8")
    keywords = derive_keywords(cv)

    con = init_db()
    rows = con.execute(
        "SELECT id,title,description,min_amount,max_amount,interval,currency FROM jobs"
    ).fetchall()
    for jid, title, desc, lo, hi, interval, currency in rows:
        vals = [v for v in (lo, hi) if v]
        monthly = to_monthly(sum(vals) / len(vals), interval, currency) if vals \
            else (salary_from_text(desc) if desc else None)
        con.execute(
            "UPDATE jobs SET score=?, has_salary=?, salary_monthly_mxn=? WHERE id=?",
            (kw_score(title or "", desc or "", keywords), monthly is not None, monthly, jid))
        con.execute(
            """INSERT INTO judgments (job_id, profile, score) VALUES (?,?,?)
               ON CONFLICT(job_id, profile) DO UPDATE SET score=excluded.score""",
            (jid, profile, kw_score(title or "", desc or "", keywords)))
    con.commit()

    pending = con.execute(
        """SELECT j.id, j.title, j.company, j.location, j.description
           FROM jobs j JOIN judgments t ON t.job_id = j.id AND t.profile = ?
           WHERE j.description != '' AND t.score > 0 AND t.fit IS NULL
           ORDER BY t.score DESC LIMIT ?""", (profile, JEV_MAX_JOBS)).fetchall()
    judged = jev_fit(con, pending, cv, profile)
    con.commit()
    con.close()
    print(f"[{profile}] {len(keywords)} keywords, scored {len(rows)} jobs, jev judged {judged}")


if __name__ == "__main__":
    main()
