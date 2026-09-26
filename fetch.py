"""Fetch jobs from Indeed/LinkedIn/Google Jobs -> SQLite. Run: python fetch.py"""
import re
import sqlite3
from datetime import datetime, timezone

from jobspy import scrape_jobs

from config import CITY, HOURS_OLD, RESULTS_WANTED, SEARCH_TERMS, init_db

# Filler words stripped from titles so cross-site postings match ("Remote
# Software Engineer" == "Software Engineer (Remote)"). ponytail: naive key;
# merge-key tuning if false matches appear in the DB.
_TITLE_STOP = {"remote", "hybrid", "remoto", "a", "the", "de", "del", "y", "el", "la", "en"}
# Corporate suffixes stripped from company names ("Acme Inc." == "acme").
_COMPANY_STOP = {"inc", "llc", "ltd", "corp", "corporation", "gmbh", "s a de c v",
                 "sa de cv", "s a", "sa", "s l", "srl", "co", "group", "solutions",
                 "de", "del", "s", "a", "c", "v", "rl", "sc", "cv"}


def _norm(s, stop):
    s = re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()
    return " ".join(w for w in s.split() if w not in stop)


def dedupe_key(title, company):
    """Cross-site identity: normalized company + title. Empty company falls back
    to title only so postings without a company still dedupe across sites."""
    return f"{_norm(company, _COMPANY_STOP)}|{_norm(title, _TITLE_STOP)}"


def num(v):
    return float(v) if v is not None and v == v else None


def txt(v):
    return str(v) if v is not None and v == v else None


def fetch(term, location, remote, google_term):
    return scrape_jobs(
        site_name=["indeed", "linkedin", "google"],
        search_term=term,
        google_search_term=google_term,
        location=location,
        is_remote=remote,
        results_wanted=RESULTS_WANTED,
        hours_old=HOURS_OLD,
        country_indeed="Mexico",
        linkedin_fetch_description=True,
    )


def save(df):
    con = init_db()
    now = datetime.now(timezone.utc).isoformat()
    new = 0
    known = {r[0] for r in con.execute("SELECT dedupe_key FROM jobs WHERE dedupe_key IS NOT NULL")}
    for r in df.itertuples():
        key = dedupe_key(txt(r.title), txt(r.company))
        if key in known:  # cross-site duplicate
            continue
        cur = con.execute(
            """INSERT OR IGNORE INTO jobs
               (site,title,company,location,job_url,description,
                min_amount,max_amount,currency,interval,is_remote,date_posted,fetched_at,dedupe_key)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (txt(r.site), txt(r.title), txt(r.company), txt(r.location), txt(r.job_url),
             r.description if isinstance(r.description, str) else "",
             num(r.min_amount), num(r.max_amount), txt(r.currency), txt(r.interval),
             int(r.is_remote) if r.is_remote is not None and r.is_remote == r.is_remote else None,
             txt(r.date_posted), now, key))
        if cur.rowcount:
            new += 1
            known.add(key)
    con.commit()
    con.close()
    return new


def backfill_dedupe():
    """One-time: stamp dedupe_key on rows saved before the column existed, then
    drop duplicates keeping the row with the longest description (Jev needs it),
    and clean up orphaned judgments."""
    con = init_db()
    missing = con.execute(
        "SELECT id, title, company FROM jobs WHERE dedupe_key IS NULL").fetchall()
    for jid, title, company in missing:
        con.execute("UPDATE jobs SET dedupe_key=? WHERE id=?",
                    (dedupe_key(title, company), jid))
    removed = 0
    for (key,) in con.execute(
            "SELECT DISTINCT dedupe_key FROM jobs WHERE dedupe_key IS NOT NULL"):
        rows = con.execute(
            "SELECT id FROM jobs WHERE dedupe_key=? ORDER BY length(COALESCE(description,'')) DESC, id DESC",
            (key,)).fetchall()
        if len(rows) > 1:  # keep the first (longest description)
            drop = [r[0] for r in rows[1:]]
            con.executemany("DELETE FROM jobs WHERE id=?", [(i,) for i in drop])
            con.executemany("DELETE FROM judgments WHERE job_id=?", [(i,) for i in drop])
            removed += len(drop)
    con.commit()
    con.close()
    if removed:
        print(f"dedupe: removed {removed} cross-site duplicates")


def main():
    backfill_dedupe()
    total = 0
    for term in SEARCH_TERMS:
        passes = [
            (True, "Mexico", f"remote {term} jobs in Mexico"),
            (False, CITY, f"{term} jobs near {CITY}, Mexico"),
        ]
        for remote, loc, gterm in passes:
            try:
                df = fetch(term, loc, remote, gterm)
                new = save(df)
                total += new
                print(f"{term} remote={remote}: {len(df)} found, {new} new")
            except Exception as e:
                print(f"{term} remote={remote} FAILED: {e}")
    print(f"done: {total} new jobs")


if __name__ == "__main__":
    main()
