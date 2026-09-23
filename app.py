"""JobHunt MX UI. Run: streamlit run app.py"""
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pandas as pd
import streamlit as st
from pypdf import PdfReader

from config import PROFILES_DIR, init_db

st.set_page_config(page_title="JobHunt MX", layout="wide")

# Password gate: enforced only when APP_PASSWORD is set (env or Streamlit Cloud secrets)
_pw = os.environ.get("APP_PASSWORD")
if _pw and st.text_input("Contraseña", type="password") != _pw:
    st.stop()

st.title("JobHunt MX")

Path(PROFILES_DIR).mkdir(exist_ok=True)

with st.sidebar:
    up = st.file_uploader("Sube tu CV (PDF)", type=["pdf"])
    if up:
        name = Path(up.name).stem
        text = "\n".join(p.extract_text() or "" for p in PdfReader(up).pages)
        Path(PROFILES_DIR, f"{name}.txt").write_text(text, encoding="utf-8")
        st.success(f"Perfil '{name}' listo")
        if Path("jobs.db").exists():
            with st.spinner(f"Puntuando vacantes para {name}..."):
                subprocess.run([sys.executable, "score.py", name], check=False)

    profiles = sorted(p.stem for p in Path(PROFILES_DIR).glob("*.txt"))
    if not profiles:
        st.warning("Sube un CV para empezar 👆")
        st.stop()
    profile = profiles[-1]

    if st.button("🔄 Actualizar vacantes", type="primary"):
        with st.spinner("Buscando y puntuando (puede tardar unos minutos)..."):
            subprocess.run([sys.executable, "fetch.py"], check=False)
            subprocess.run([sys.executable, "score.py", profile], check=False)
        st.rerun()

    salary_only = st.checkbox("Solo con sueldo publicado")
    mod = st.selectbox("Modalidad", ["Todas", "Remoto", "Presencial/Híbrido"])
    min_fit = st.slider("Fit mínimo (Jev)", 0.0, 1.0, 0.0, 0.05)
    q = st.text_input("Buscar en título/descripción")

con = init_db()
df = pd.read_sql(
    """SELECT j.id, j.site, j.title, j.company, j.location, j.job_url, j.description,
              j.is_remote, j.date_posted, j.has_salary, j.salary_monthly_mxn,
              t.score AS pscore, t.fit, t.jev_skill, t.jev_seniority
       FROM jobs j LEFT JOIN judgments t ON t.job_id = j.id AND t.profile = ?""",
    con, params=(profile,))
con.close()

if df.empty:
    st.info("Sin vacantes todavía — pulsa **Actualizar vacantes** en la barra lateral.")
    st.stop()

df["sueldo"] = df.salary_monthly_mxn.apply(
    lambda v: f"${v:,.0f}/mes" if pd.notna(v) else "")

all_sites = sorted(df.site.dropna().unique())
sites = st.sidebar.multiselect("Fuente", all_sites, default=all_sites)

f = df[df.site.isin(sites)]
if salary_only:
    f = f[f.has_salary == 1]
if mod == "Remoto":
    f = f[f.is_remote == 1]
elif mod != "Todas":
    f = f[f.is_remote != 1]
if min_fit:
    f = f[f.fit >= min_fit]
if q:
    f = f[f.title.str.contains(q, case=False, na=False)
          | f.description.str.contains(q, case=False, na=False)]

f = f.sort_values(["has_salary", "fit", "pscore"], ascending=False, na_position="last")
st.caption(f"{len(f)} vacantes para **{profile}** · orden: con sueldo primero, luego por fit de Jev")
st.dataframe(
    f[["title", "company", "location", "sueldo", "fit", "jev_skill",
       "jev_seniority", "site", "date_posted", "job_url"]],
    column_config={
        "job_url": st.column_config.LinkColumn("link", display_text="abrir"),
        "fit": st.column_config.ProgressColumn("fit", min_value=0.0, max_value=1.0, format="%.2f"),
        "jev_skill": st.column_config.NumberColumn("skill", format="%.2f"),
        "jev_seniority": st.column_config.NumberColumn("seniority", format="%.2f"),
    },
    hide_index=True,
    use_container_width=True,
    height=650,
)
