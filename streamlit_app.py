"""SilverFile Streamlit app (D8): `streamlit run streamlit_app.py`.

Pages: the Kushim staff dashboard (P7). P3's taxpayer intake page is added automatically when
src/ui/taxpayer_page.py exists and defines `page()`, so neither workstream edits the other's file.
"""
from pathlib import Path

import streamlit as st

from src.dashboard.auth import load_env_file

load_env_file()
st.set_page_config(page_title="SilverFile", page_icon=":material/description:", layout="wide")

from src.dashboard.app import page as staff_page  # noqa: E402  (after set_page_config)

pages = [st.Page(staff_page, title="Staff dashboard", icon=":material/dashboard:", url_path="staff", default=True)]
if (Path(__file__).parent / "src" / "ui" / "taxpayer_page.py").is_file():
    from src.ui.taxpayer_page import page as taxpayer_page  # P3
    pages.insert(0, st.Page(taxpayer_page, title="Taxpayer", icon=":material/chat:", url_path="taxpayer"))
st.navigation(pages).run()
