import streamlit as st
import pandas as pd
from github import Github  # veillez à avoir "PyGithub" dans requirements.txt
from serpapi import GoogleSearch
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO  # pour l'export XLSX

# ────────────────────────────────────────────────────
# 1. Gestion des secrets (.streamlit/secrets.toml)
# ────────────────────────────────────────────────────
try:
    SERPAPI_KEY = st.secrets["serpapi_key"]
except Exception:
    st.error("❌ Clé SerpApi manquante dans `.streamlit/secrets.toml`.")
    st.stop()

GITHUB_TOKEN = st.secrets.get("github_token", None)  # facultatif mais ↑ quota GitHub API

# ────────────────────────────────────────────────────
# 2. Paramètres UI (sidebar)
# ────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Paramètres")
    hl = st.selectbox("Langue (hl)", ["fr", "en", "es", "de", "it"], index=0)
    gl = st.selectbox("Pays (gl)", ["fr", "us", "es", "de", "it"], index=0)
    max_workers = st.slider("Threads simultanés", min_value=1, max_value=16, value=8)

# ────────────────────────────────────────────────────
# 3. Lecture de queries.txt depuis GitHub (public)
# ────────────────────────────────────────────────────
GITHUB_REPO = "thibault60/scraper-SERP"  # modifiez si vous forkez
QUERY_FILE = "queries.txt"

github = Github(GITHUB_TOKEN) if GITHUB_TOKEN else Github()
try:
    repo = github.get_repo(GITHUB_REPO)
    contents = repo.get_contents(QUERY_FILE)
    raw_txt = requests.get(contents.download_url).text
    queries = [line.strip() for line in raw_txt.splitlines() if line.strip()]
except Exception as e:
    st.error(f"Impossible de lire `{QUERY_FILE}` depuis le dépôt : {e}")
    st.stop()

# ────────────────────────────────────────────────────
# 4. Fonction d’extraction des PAA (People Also Ask)
# ────────────────────────────────────────────────────

def get_paa(query: str) -> list[dict]:
    """Interroge SerpApi et renvoie la liste des blocs PAA."""
    params = {
        "q": query,
        "api_key": SERPAPI_KEY,
        "hl": hl,
        "gl": gl,
        "num": 10,
    }
    search = GoogleSearch(params)
    results = search.get_dict()
    return results.get("related_questions", [])

# ────────────────────────────────────────────────────
# 5. Collecte parallèle + cache
# ────────────────────────────────────────────────────

def fetch_paa_single(query: str) -> list[dict]:
    """Récupère les PAA pour une requête donnée et retourne une liste de dicts."""
    try:
        paa_items = get_paa(query)
        if paa_items:
            return [
                {
                    "Requête": query,
                    "Question PAA": item.get("question", "—"),
                    "Réponse": item.get("snippet") or item.get("answer") or "—",
                    "Source": item.get("link", ""),
                }
                for item in paa_items
            ]
        # Pas de PAA
        return [
            {
                "Requête": query,
                "Question PAA": "—",
                "Réponse": "—",
                "Source": "",
            }
        ]
    except Exception as exc:
        return [
            {
                "Requête": query,
                "Question PAA": "—",
                "Réponse": f"Erreur : {exc}",
                "Source": "",
            }
        ]

@st.cache_data(ttl=86_400, show_spinner=False)
def fetch_paa_parallel(queries_list: list[str], workers: int) -> pd.DataFrame:
    """Collecte les PAA en parallèle avec une barre de progression."""
    rows: list[dict] = []
    progress = st.progress(0.0, text="🔄 Récupération des PAA …")
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(fetch_paa_single, q): q for q in queries_list}
        total = len(futures)
        for i, future in enumerate(as_completed(futures), 1):
            rows.extend(future.result())
            progress.progress(i / total)
    progress.empty()
    return pd.DataFrame(rows)

# ────────────────────────────────────────────────────
# 6. Interface Streamlit
# ────────────────────────────────────────────────────

st.set_page_config(page_title="Scraper PAA SERP", layout="wide")
st.title("🤖 Extraction des PAA Google – scraper-SERP")
st.markdown(
    "Cette application lit `queries.txt` depuis GitHub, interroge SerpApi et affiche les blocs **People Also Ask** (PAA)."
)

if st.button("🕹️ Extraire les PAA"):
    df_paa = fetch_paa_parallel(queries, max_workers)

    st.dataframe(
        df_paa,
        use_container_width=True,
        height=600,
        column_order=["Requête", "Question PAA", "Réponse", "Source"],
    )

    # Téléchargement CSV
    csv = df_paa.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="💾 Télécharger le CSV",
        data=csv,
        file_name="paa_results.csv",
        mime="text/csv",
    )

    # Téléchargement XLSX
    xlsx_buffer = BytesIO()
    with pd.ExcelWriter(xlsx_buffer, engine="xlsxwriter") as writer:  # nécessite `xlsxwriter` dans requirements.txt
        df_paa.to_excel(writer, index=False, sheet_name="PAA")
    xlsx_buffer.seek(0)
    st.download_button(
        label="📊 Télécharger le XLSX",
        data=xlsx_buffer,
        file_name="paa_results.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    # Affichage détaillé (groupé par requête)
    for query in df_paa["Requête"].unique():
        subset = df_paa[df_paa["Requête"] == query]
        with st.expander(f"🔍 {query} — {len(subset)} questions"):
            for _, r in subset.iterrows():
                st.markdown(f"**Q :** {r['Question PAA']}")
                if r["Réponse"] not in ("—", ""):
                    st.markdown(r["Réponse"])
                if r["Source"]:
                    st.caption(r["Source"])
                st.markdown("---")
