import streamlit as st
import pandas as pd
from github import Github  # veillez à avoir "PyGithub" dans requirements.txt
from serpapi import GoogleSearch
import requests

# ────────────────────────────────────────────────────
# 1. Gestion des secrets (.streamlit/secrets.toml)
# ────────────────────────────────────────────────────
# Créez un fichier .streamlit/secrets.toml contenant :
# serpapi_key = "VOTRE_CLE_SERPAPI"
SERPAPI_KEY = st.secrets["serpapi_key"]

# ────────────────────────────────────────────────────
# 2. Lecture de queries.txt depuis GitHub (public)
# ────────────────────────────────────────────────────
GITHUB_REPO = "thibault60/scraper-SERP"  # laissez vide pour forker plus tard
QUERY_FILE = "queries.txt"

github = Github()  # accès en lecture seule aux dépôts publics
repo = github.get_repo(GITHUB_REPO)
contents = repo.get_contents(QUERY_FILE)
raw_txt = requests.get(contents.download_url).text

# Chaque ligne de queries.txt est considérée comme une requête
queries = [line.strip() for line in raw_txt.splitlines() if line.strip()]

# ────────────────────────────────────────────────────
# 3. Fonction d’extraction des PAA (People Also Ask)
# ────────────────────────────────────────────────────

def get_paa(query: str) -> list[dict]:
    """Interroge SerpApi et renvoie la liste des blocs PAA."""
    params = {
        "q": query,
        "api_key": SERPAPI_KEY,
        "hl": "fr",
        "gl": "fr",
        "num": 10,
    }
    search = GoogleSearch(params)
    results = search.get_dict()
    return results.get("related_questions", [])  # Clé JSON pour les PAA

# ────────────────────────────────────────────────────
# 4. Mise en cache pour limiter les appels API
# ────────────────────────────────────────────────────

@st.cache_data(show_spinner="🔄 Récupération des PAA …")
def fetch_paa(queries_list: list[str]) -> pd.DataFrame:
    """Boucle sur chaque requête et génère un DataFrame à plat."""
    rows = []
    for q in queries_list:
        paa_items = get_paa(q)
        if paa_items:
            for item in paa_items:
                rows.append(
                    {
                        "Requête": q,
                        "Question PAA": item.get("question", "—"),
                        "Réponse": item.get("snippet")
                        or item.get("answer")
                        or "—",
                        "Source": item.get("link", ""),
                    }
                )
        else:
            rows.append(
                {
                    "Requête": q,
                    "Question PAA": "—",
                    "Réponse": "—",
                    "Source": "",
                }
            )
    return pd.DataFrame(rows)

# ────────────────────────────────────────────────────
# 5. Interface Streamlit
# ────────────────────────────────────────────────────

st.set_page_config(page_title="Scraper PAA SERP", layout="wide")
st.title("🤖 Extraction des PAA Google – scraper-SERP")
st.markdown(
    "Cette application lit `queries.txt` depuis GitHub, interroge SerpApi et affiche les blocs *People Also Ask* (PAA)."
)

if st.button("🕹️ Extraire les PAA"):
    df_paa = fetch_paa(queries)
    st.dataframe(df_paa, use_container_width=True)

    # Téléchargement CSV
    csv = df_paa.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="💾 Télécharger le CSV",
        data=csv,
        file_name="paa_results.csv",
        mime="text/csv",
    )

    # Affichage détaillé (groupé par requête)
    for query in df_paa["Requête"].unique():
        subset = df_paa[df_paa["Requête"] == query]
        with st.expander(f"🔍 {query} — {len(subset)} questions"):
            for _, r in subset.iterrows():
                st.markdown(f"**Q:** {r['Question PAA']}")
                if r["Réponse"] != "—":
                    st.markdown(r["Réponse"])
                if r["Source"]:
                    st.caption(r["Source"])
                st.markdown("---")
