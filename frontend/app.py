import streamlit as st
import requests
import os
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(page_title="AI Code Optimizer", layout="wide")

st.title("AI Code Complexity Optimizer")
st.subheader("Improve Time & Space Complexity with AI")

backend_url = os.getenv("BACKEND_URL")

repo_url = st.text_input("GitHub Repository URL")

@st.cache_data
def fetch_branches(repo_url):
    try:
        parts = repo_url.strip("/").split("/")
        owner, repo = parts[-2], parts[-1]

        url = f"https://api.github.com/repos/{owner}/{repo}/branches"

        headers = {"Authorization": f"Bearer {os.getenv('GITHUB_TOKEN')}"}
        response = requests.get(url, headers=headers)

        if response.status_code != 200:
            return []

        return [b["name"] for b in response.json()]
    except:
        return []

branches = fetch_branches(repo_url) if repo_url else []

branch = st.selectbox("Select Branch", branches) if branches else "main"

# 🔥 Toggle view
view_mode = st.radio(
    "View Mode",
    ["Side-by-Side", "Optimized Only"],
    horizontal=True
)

if st.button("Analyze & Optimize"):
    if not repo_url:
        st.error("Enter a repo URL")
    else:
        with st.spinner("Analyzing code..."):
            payload = {"repo_url": repo_url, "branch": branch}
            response = requests.post(backend_url, json=payload)

            if response.status_code != 200:
                st.error("Backend error")
                st.stop()

            data = response.json()
            st.success(f"Analysis complete: {data['repo_name']}")

            for s in data["suggestions"]:
                with st.expander(f"📄 {s['file_path']}", expanded=True):

                    col1, col2 = st.columns(2)

                    with col1:
                        st.markdown("### 📊 Metrics")
                        st.error(f"Current: {s['original_complexity']}")
                        st.success(f"Optimized: {s['optimized_complexity']}")
                        st.info(s["explanation"])

                    if view_mode == "Side-by-Side":
                        colA, colB = st.columns(2)

                        with colA:
                            st.markdown("### 🧾 Current Code")
                            st.code(s["original_code"])

                        with colB:
                            st.markdown("### ⚡ Optimized Code")
                            st.code(s["refactored_code"])

                    else:
                        st.markdown("### ⚡ Optimized Code")
                        st.code(s["refactored_code"])

                    st.divider()

st.caption("Built with FastAPI + LangChain + FAISS + Streamlit")