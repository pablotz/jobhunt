"""Fetch jobs from Indeed/LinkedIn/Google Jobs -> SQLite. Run: python fetch.py"""
import sqlite3
from datetime import datetime, timezone

from jobspy import scrape_jobs

from config import CITY, HOURS_OLD, RESULTS_WANTED, SEARCH_TERMS, init_db


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
    for r in df.itertuples():
        cur = con.execute(
            """INSERT OR IGNORE INTO jobs
               (site,title,company,location,job_url,description,
                min_amount,max_amount,currency,interval,is_remote,date_posted,fetched_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (txt(r.site), txt(r.title), txt(r.company), txt(r.location), txt(r.job_url),
             r.description if isinstance(r.description, str) else "",
             num(r.min_amount), num(r.max_amount), txt(r.currency), txt(r.interval),
             int(r.is_remote) if r.is_remote is not None and r.is_remote == r.is_remote else None,
             txt(r.date_posted), now))
        new += cur.rowcount
    con.commit()
    con.close()
    return new


def main():
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
