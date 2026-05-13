import streamlit as st
import requests
import os
from dotenv import load_dotenv
from PIL import Image

load_dotenv()

favicon = Image.open("images/favicon.ico")

st.set_page_config(
    page_title="AI Code Optimizer",
    page_icon=favicon,
    layout="wide"
)

st.title("AI Code Complexity Optimizer")
st.subheader("Improve Time & Space Complexity with AI")
st.caption("Optimization runs when a new commit is detected")

backend_url = os.getenv("BACKEND_URL")
headers = {
    "Authorization": f"Bearer {os.getenv('GITHUB_TOKEN')}"
}

repo_url = st.text_input("GitHub Repository URL", key="repo_input")

@st.cache_data(show_spinner=False)
def fetch_branches(repo_url):
    try:
        parts = repo_url.strip("/").split("/")
        owner, repo = parts[-2], parts[-1]

        url = (f"https://api.github.com/repos/{owner}/{repo}/branches")

        response = requests.get(url, headers=headers, timeout=30)

        if response.status_code != 200:
            return []

        return [b["name"] for b in response.json()]

    except Exception as e:
        print("Branch fetch error:", e)
        return []

branches = (fetch_branches(repo_url) if repo_url else [])

if not branches:
    branches = ["main"]

branch = st.selectbox("Select Branch", branches, key="branch_select")

@st.cache_data(show_spinner=False)
def fetch_latest_commit(repo_url, branch):
    try:
        parts = repo_url.strip("/").split("/")
        owner, repo = parts[-2], parts[-1]

        url = (f"https://api.github.com/repos/{owner}/{repo}/commits/{branch}")

        response = requests.get(url, headers=headers, timeout=30)

        if response.status_code != 200:
            return None

        data = response.json()

        return {
            "sha": data.get("sha", ""),
            "message": (
                data.get("commit", {})
                .get("message", "")
            ),
            "author": (
                data.get("commit", {})
                .get("author", {})
                .get("name", "")
            ),
            "date": (
                data.get("commit", {})
                .get("author", {})
                .get("date", "")
            ),
        }

    except Exception as e:
        print("Commit fetch error:", e)
        return None

commit_info = None

if repo_url:
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

def detect_language(file_path):
    file_path = str(file_path)

    if file_path.endswith(".py"):
        return "python"

    if (file_path.endswith(".js", ".jsx")):
        return "javascript"

    if file_path.endswith(".java"):
        return "java"

    if file_path.endswith(".cpp"):
        return "cpp"

    if file_path.endswith(".c"):
        return "c"

    return "text"

def safe_text(value):
    if value is None:
        return ""

    if isinstance(value, (dict, list)):
        return str(value)

    return str(value)

if st.button("Analyze & Optimize"):

    if not repo_url:
        st.error("Enter a GitHub repository URL")
        st.stop()

    with st.spinner("Analyzing code..."):

        payload = {
            "repo_url": repo_url,
            "branch": branch
        }

        try:
            response = requests.post(backend_url, json=payload, timeout=300)

        except Exception as e:
            st.error(f"Connection Error: {e}")
            st.stop()

        if response.status_code != 200:
            st.error(f"Backend Error ({response.status_code})")
            st.code(response.text)
            st.stop()

        try:
            data = response.json()

        except Exception as e:
            st.error(f"Invalid JSON response: {e}")
            st.code(response.text)
            st.stop()

        with st.expander("Raw Backend Response"):
            st.json(data)

        st.success(f"Analysis complete: {data.get('repo_name', 'Unknown Repo')}")

        suggestions = data.get("suggestions", [])

        if not suggestions:
            st.warning("No optimization suggestions found.")
            st.stop()

        st.write(f"### Total Suggestions: {len(suggestions)}")

        for i, s in enumerate(suggestions):
            try:
                if not isinstance(s, dict):
                    st.error(f"Suggestion {i+1} is not a dictionary")
                    st.write(s)
                    continue

                file_path = safe_text(s.get("file_path", "Unknown File"))

                language = detect_language(file_path)

                original_complexity = safe_text(s.get("original_complexity", "Unknown"))

                optimized_complexity = safe_text(s.get("optimized_complexity", "Unknown"))

                explanation = safe_text(s.get("explanation", "No explanation"))

                original_code = safe_text(s.get("original_code", ""))

                refactored_code = safe_text(s.get("refactored_code", ""))

                with st.expander(f"📄 Suggestion {i+1}: {file_path}", expanded=False):
                    st.markdown("### 📊 Complexity")

                    col1, col2 = st.columns(2)

                    with col1:
                        st.error(f"Current: {original_complexity}")
                        st.success(f"Optimized: {optimized_complexity}")

                    with col2:
                        st.info(explanation)
                        
                    colA, colB = st.columns(2)
                    
                    with colA:
                        st.markdown("### 🧾 Current Code")
                        st.code(original_code, language=language)

                    with colB:
                        st.markdown("### ⚡ Optimized Code")
                        st.code(refactored_code, language=language)

            except Exception as e:
                st.error(f"Failed to render suggestion {i+1}: {e}")
                st.write("Raw suggestion:")
                st.write(s)

st.divider()

st.caption("Built with FastAPI + LangChain + FAISS + Streamlit")