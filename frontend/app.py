import streamlit as st
import requests
import os
from dotenv import load_dotenv
from PIL import Image

load_dotenv()

favicon = Image.open("favicon.png")
st.set_page_config(page_title="AI Code Optimizer", page_icon=favicon, layout="wide")

st.title("AI Code Complexity Optimizer")
st.subheader("Improve Time & Space Complexity with AI")
st.caption("Optimization runs when a new commit is detected")

backend_url = os.getenv("BACKEND_URL")

repo_url = st.text_input("GitHub Repository URL", key="repo_input")

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
    except Exception:
        return []

branches = fetch_branches(repo_url) if repo_url else []

if not branches:
    branches=["main"]
    
branch = st.selectbox("Select Branch", branches, key="branch_select")

@st.cache_data
def fetch_latest_commit(repo_url, branch):
    try:
        parts = repo_url.strip("/").split("/")
        owner, repo = parts[-2], parts[-1]

        url = f"https://api.github.com/repos/{owner}/{repo}/commits/{branch}"

        headers = {
            "Authorization": f"Bearer {os.getenv('GITHUB_TOKEN')}"
        }

        response = requests.get(url, headers=headers)

        if response.status_code != 200:
            return None

        data = response.json()

        return {
            "sha": data.get("sha"),
            "message": data.get("commit", {}).get("message"),
            "author": data.get("commit", {}).get("author", {}).get("name"),
            "date": data.get("commit", {}).get("author", {}).get("date"),
        }
        
    except Exception as e:
        print("Commit fetch error: ", e)
        return None

commit_info = None

if repo_url and branches:
    with st.spinner("Fetching latest commit..."):
        commit_info = fetch_latest_commit(repo_url, branch)

if commit_info:
    st.markdown("### 🔄 Latest Commit")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.write(f"**Commit SHA:** {commit_info['sha'][:10]}")

    with col2:
        st.write(f"**Author:** {commit_info['author']}")

    with col3: 
        st.write(f"**Date:** {commit_info['date']}")

    st.info(f"📝 {commit_info['message']}")

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
                    st.markdown("### 📊 Metrics")
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.error(f"Current: {s['original_complexity']}")
                        st.success(f"Optimized: {s['optimized_complexity']}")
                    with col2:
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