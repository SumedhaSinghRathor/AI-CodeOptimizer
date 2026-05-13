import streamlit as st
import requests
from PIL import Image
from cookie_manager import get_cookie_manager
import json

favicon = Image.open("images/favicon.ico")

st.set_page_config(
    page_title="Analysis",
    page_icon=favicon,
    layout="wide"
)

pages = {
    "Pages": [
        st.Page("hero.py", title="New Page"),
        st.Page("pages/page_1.py", title="Page 1"),
        st.Page("pages/page_2.py", title="Page 2")
    ]
}

pg = st.navigation(pages)
pg.run()

cookies = get_cookie_manager()

if not cookies.ready():
    st.stop()

query_params = st.query_params
token = query_params.get("token")
username = query_params.get("username")
github_token = query_params.get("github_token")

if token and username and github_token:
    cookies["token"] = token
    cookies["username"] = username
    cookies["github_token"] = github_token
    cookies.save()

    st.query_params.clear()

saved_token = cookies.get("token")
saved_username = cookies.get("username")
saved_github_token = cookies.get("github_token")

if saved_token and saved_username and saved_github_token:
    st.session_state["token"] = saved_token
    st.session_state["username"] = saved_username
    st.session_state["github_token"] = saved_github_token

@st.cache_data(ttl=300)
def fetch_user_repos(github_token):
    repos = []
    page = 1

    while True:
        response = requests.get(
            "https://api.github.com/user/repos",
            headers={
                "Authorization": f"Bearer {github_token}"
            },
            params={
                "per_page": 100,
                "page": page,
                "sort": "updated"
            }
        )

        if response.status_code != 200:
            return []
        
        data = response.json()
        if not data:
            break

        repos.extend(data)
        page += 1

    return repos

with open('../backend/cache/SumedhaSinghRathor_sample_main_946e3a5612675b3b5b5f30717288ede8c5cf3ac0.json', 'r') as f:
    data = json.load(f)

is_logged_in = (
    st.session_state.get("token") is not None
    and st.session_state.get("username") is not None
)

st.header("AI Code Complexity Optimizer", divider="gray")

if not is_logged_in:
    st.text("This FastAPI project integrates the GitHub API to fetch source code and utilizes DeepSeek’s reasoning capabilities to analyze performance bottlenecks.", text_alignment="center")

    st.link_button(
        "Login with GitHub",
        "http://localhost:8000/auth/github/login",
        use_container_width=True,
        type="primary"
    )

else:
    col1, col2 = st.columns([9, 1], vertical_alignment="center")
    with col1:
        st.write(f"Hello, **@{st.session_state['username']}**. You are logged in")
    with col2:
        if st.button("Logout", use_container_width=True):
            del cookies["token"]
            del cookies["username"]
            del cookies["github_token"]
            
            cookies.save()
            st.session_state.clear()
            st.query_params.clear()
            st.rerun()

    col1, col2 = st.columns([1, 3])

    with col1:
        st.write("**Source Code**")
    
    with col2:
        tab1, tab2 = st.tabs(["Git Provider", "Public Git Repository"])

        with tab1:
            repos = fetch_user_repos(st.session_state["github_token"])
            repo_names = [repo["full_name"] for repo in repos]
            selected_repo = st.selectbox("Search for repositories", options=repo_names, index=None, placeholder="Type to search repositories...")

            selected_repo_data = next((repo for repo in repos if repo["full_name"] == selected_repo), None)

            if selected_repo_data:
                repo_url = selected_repo_data["html_url"]

        with tab2:
            st.text_input("You can enter any public repository link here", icon=":material/language:")

    st.markdown("### 🔄 Latest Commit")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.write(
            f"**Commit SHA:** "
            # f"{commit_info['sha'][:10]}"
            "49ee27bbc8"
        )

    with col2:
        st.write(
            f"**Author:** "
            # f"{commit_info['author']}"
            "SumedhaSinghRathor"
        )

    with col3:
        st.write(
            f"**Date:** "
            # f"{commit_info['date']}"
            "2026-03-05T08:26:53Z"
        )

    st.info(
        # f"📝 {commit_info['message']}"
        "📝 update frontend to recieve data from backend"
    )

    st.button("Analyze & Optimize", type="primary", width="stretch")

    st.success(f"Analysis complete: {data['repo_name']}")



for suggestion in data['suggestions']:
    with st.expander(f"{suggestion['file_path']}", expanded=True):
        st.markdown("### 📊 Metrics")

        col1, col2 = st.columns(2)

        with col1:
            st.error(f"Current: {suggestion['original_complexity']}")
            st.success(f"Optimized: {suggestion['optimized_complexity']}")

        with col2:
            st.info(suggestion['explanation'])

        col3, col4 = st.columns(2)

        with col3:
            st.markdown("### 🧾 Current Code")
            st.code(suggestion['original_code'])
        
        with col4:
            st.markdown("### ⚡ Optimized Code")
            st.code(suggestion['refactored_code'])

st.divider()

st.caption("Built with FastAPI + LangChain + FAISS + Streamlit")

pg = st.navigation(pages)
pg.run()