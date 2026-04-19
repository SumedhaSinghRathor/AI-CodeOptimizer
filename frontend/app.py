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
branch = st.text_input("Branch (optional)", value="main")

if st.button("Analyze & Optimize"):
    if not repo_url:
        st.error("Please provide a repository URL")
    else:
        with st.spinner("AI is reading your code and calculating complexities..."):
            try:
                payload = {"repo_url": repo_url, "branch": branch}
                response = requests.post(backend_url, json=payload)
                
                if response.status_code == 200:
                    data = response.json()
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