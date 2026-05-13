import streamlit as st
from streamlit_cookies_manager import EncryptedCookieManager

@st.cache_resource
def get_cookie_manager():
    cookies = EncryptedCookieManager(
        prefix="ai_optimizer_",
        password="super-secret-password"
    )

    return cookies