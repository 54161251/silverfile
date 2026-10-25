"""SilverFile Streamlit app (D8): `streamlit run streamlit_app.py`.

Pages: Taxpayer (one Intake question at a time, src/ui/taxpayer_page.py) and the Kushim staff
dashboard (src/dashboard/app.py). Both are P7 UI; Intake's question/answer contract is P3's
(docs/P1_INTAKE_HANDOFF.md).
"""
import streamlit as st

from src.dashboard.auth import load_env_file

load_env_file()
st.set_page_config(page_title="SilverFile", page_icon=":material/description:", layout="wide")

from src.dashboard.app import page as staff_page  # noqa: E402  (after set_page_config)
from src.ui.taxpayer_page import page as taxpayer_page  # noqa: E402

st.navigation([
    st.Page(taxpayer_page, title="Taxpayer", icon=":material/chat:", url_path="taxpayer", default=True),
    st.Page(staff_page, title="Staff dashboard", icon=":material/dashboard:", url_path="staff"),
]).run()
