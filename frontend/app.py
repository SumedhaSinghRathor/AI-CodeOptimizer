import streamlit as st
import requests
import time
import os
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(page_title="AI Code Optimizer", layout="wide")

st.title("AI Code Complexity Optimizer")
st.subheader("Submit a GitHub Repo to improve Time & Space Complexity")

backend_url = os.getenv("BACKEND_URL")
    
repo_url = st.text_input("GitHub Public Repository URL", placeholder="https://github.com")

@st.cache_data
def fetch_branches(repo_url):
    try:
        parts = repo_url.strip("/").split("/")
        owner, repo = parts[-2], parts[-1]
        
        url = f"https://api.github.com/repos/{owner}/{repo}/branches"

        headers = {
            "Authorization": f"Bearer {os.getenv('GITHUB_TOKEN')}"
        }
        
        response = requests.get(url, headers=headers)

        if response.status_code != 200:
            return []

        data = response.json()
        return [branch["name"] for branch in data]
    
    except Exception as e:
        print("Branch fetch error:", e)
        return []
    
branches = []
if repo_url:
    with st.spinner("Fetching branches..."):
        branches = fetch_branches(repo_url)
    
branch = st.selectbox("Select Branch", branches, index=0)

if st.button("Analyze & Optimize"):
    if not repo_url:
        st.error("Please provide a repository URL")
    else:
        with st.spinner("AI is reading your code and calculating complexities..."):
            try:
                payload = {"repo_url": repo_url, "branch": branch}
                response = requests.post(backend_url, json=payload)
                
                if response.status_code == 200:
                    try:
                        data = response.json()
                    except Exception:
                        st.error(f"Invalid response from backend: {response.text}")
                        st.stop()
                    st.success(f"Analysis complete for: {data['repo_name']}")
                    
                    for idx, suggestion in enumerate(data['suggestions']):
                        with st.expander(f"File: {suggestion['file_path']}", expanded=True):
                            col1, col2 = st.columns(2)
                            
                            with col1:
                                st.markdown("### 📊 Metrics")
                                st.error(f"**Current:** {suggestion['original_complexity']}")
                                st.success(f"**Proposed:** {suggestion['optimized_complexity']}")
                                st.info(f"**Explanation:** {suggestion['explanation']}")
                            with col2:
                                st.markdown("### 💡 AI Suggestion")
                                st.code(suggestion['refactored_code'], language='python')
                            st.divider()
                else:
                    st.error(f"Error: {response.json().get('detail', 'Unknown error occured')}")
            except Exception as e:
                st.error(f"Could not connect to backend: {e}")
                
st.markdown("----")
st.caption("Built with FastAPI, LangChain, DeepSeek, and Streamlit.")