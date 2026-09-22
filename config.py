"""JobHunt MX — configuration."""
import os
import sqlite3
from pathlib import Path

DB = "jobs.db"
PROFILES_DIR = "profiles"   # one <name>.txt per person (uploaded via the UI)

# Where to search: remote (Mexico-wide) + onsite/hybrid in this city
CITY = "León, Guanajuato"

# One scrape pass per term per mode (remote/city). Keep short: each pass costs time.
SEARCH_TERMS = ["software engineer", "full stack developer", "node.js developer"]
RESULTS_WANTED = 30   # per site per pass
HOURS_OLD = 168       # postings from the last week

# Tech vocabulary: a profile's keywords = the terms found in its CV text.
# False positives only cost a few extra Jev judgments; missing terms cost coverage.
VOCAB = [
    "javascript", "typescript", "python", "node", "react", "angular", "vue",
    "express", "next.js", "django", "flask", "fastapi", "spring", "java",
    "kotlin", "swift", "golang", "rust", "c++", "c#", ".net", "php", "laravel",
    "ruby", "rails", "aws", "azure", "gcp", "terraform", "docker", "kubernetes",
    "jenkins", "ci/cd", "github", "gitlab", "sql", "mysql", "postgres",
    "mongodb", "dynamodb", "redis", "graphql", "api", "rest", "microservices",
    "serverless", "lambda", "playwright", "cypress", "selenium", "jest",
    "agile", "scrum", "linux", "bash", "tailwind", "css", "html",
    "react native", "flutter", "machine learning", "etl", "spark", "airflow",
]

# Jev: max jobs judged per profile per score run (top keyword scorers first)
JEV_MAX_JOBS = 50
WEIGHT_SKILL = 0.7
WEIGHT_SENIORITY = 0.3

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
  id INTEGER PRIMARY KEY,
  site TEXT, title TEXT, company TEXT, location TEXT,
  job_url TEXT UNIQUE, description TEXT,
  min_amount REAL, max_amount REAL, currency TEXT, interval TEXT,
  is_remote INTEGER, date_posted TEXT, fetched_at TEXT,
  score REAL, has_salary INTEGER, salary_monthly_mxn REAL
);
CREATE TABLE IF NOT EXISTS judgments (
  job_id INTEGER, profile TEXT,
  score REAL,
  jev_skill REAL, jev_seniority REAL, jev_english REAL, jev_remote REAL,
  fit REAL, PRIMARY KEY (job_id, profile)
)"""


def load_env():
    for line in Path(".env").read_text().splitlines() if Path(".env").exists() else []:
        if "=" in line and not line.startswith("#"):
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())


load_env()


def init_db(path=DB):
    con = sqlite3.connect(path)
    for stmt in SCHEMA.split(";"):
        con.execute(stmt)
    try:  # pre-multi-profile dbs: judgments exists without score column
        con.execute("ALTER TABLE judgments ADD COLUMN score REAL")
    except sqlite3.OperationalError:
        pass
    return con
