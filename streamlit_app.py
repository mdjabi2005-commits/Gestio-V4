import os
import uuid
from datetime import date

import streamlit as st

from enable_banking_service import EnableBankingService

st.set_page_config(page_title="Enable Banking Sandbox", layout="centered")

st.title("Enable Banking Sandbox")

st.write("This app uses the Enable Banking REST API and Streamlit redirect flow.")


def _get_secret(name: str) -> str:
    if name in st.secrets:
        return st.secrets[name]
    return os.getenv(name, "")


def _normalize_private_key(key: str) -> str:
    # Allow multiline keys stored with \n in env vars
    return key.replace("\\n", "\n").strip()


app_id = _get_secret("ENABLE_APP_ID")
private_key = _normalize_private_key(_get_secret("ENABLE_PRIVATE_KEY"))

if not app_id or not private_key:
    st.warning("Set ENABLE_APP_ID and ENABLE_PRIVATE_KEY (env or Streamlit secrets).")
    st.stop()

service = EnableBankingService(application_id=app_id, private_key_pem=private_key)

country = st.selectbox("Country", ["FR", "DE", "ES", "IT", "NL", "BE"])

aspsps = service.get_aspsps(country=country)
if not aspsps:
    st.info("No banks returned for this country. Try another.")
    st.stop()

st.caption(f"Banks returned: {len(aspsps)}")
with st.expander("Show banks returned (debug)"):
    st.json(aspsps[:10])

aspsp_names = [a.get("name", "") for a in aspsps]
selected_aspsp = st.selectbox("Bank", aspsp_names)

redirect_url = "http://localhost:8501/"

col1, col2 = st.columns(2)
with col1:
    create_link = st.button("Create auth link")

if create_link:
    oauth_state = uuid.uuid4().hex
    st.session_state["oauth_state"] = oauth_state
    auth = service.start_auth(
        aspsp_name=selected_aspsp,
        country=country,
        redirect_url=redirect_url,
        state=oauth_state,
    )
    st.session_state["auth"] = auth

if "auth" in st.session_state:
    auth = st.session_state["auth"]
    auth_url = auth.get("url")
    if auth_url:
        st.link_button("Open bank login", auth_url)

params = st.query_params
code = params.get("code")
state = params.get("state")

if isinstance(code, list):
    code = code[0]
if isinstance(state, list):
    state = state[0]

if code:
    last_code = st.session_state.get("last_code")
    if last_code != code:
        expected_state = st.session_state.get("oauth_state")
        if expected_state and state and state != expected_state:
            st.error("State mismatch. Do not continue.")
            st.stop()

        session = service.exchange_code(code)
        st.session_state["session"] = session
        st.session_state["last_code"] = code

if "session" in st.session_state:
    session = st.session_state["session"]
    session_id = session.get("session_id")
    st.success(f"Session created: {session_id}")

    accounts = session.get("accounts", [])
    if not accounts:
        session_details = service.get_session(session_id)
        accounts = session_details.get("accounts", [])

    if not accounts:
        st.info("No accounts returned yet. Try again later.")
        st.stop()

    account_ids = [a.get("id", "") for a in accounts]
    selected_account = st.selectbox("Account", account_ids)

    col_a, col_b = st.columns(2)
    with col_a:
        date_from = st.date_input("Date from", value=date(2026, 1, 1))
    with col_b:
        date_to = st.date_input("Date to", value=date.today())

    if st.button("Fetch transactions"):
        txs = service.fetch_all_transactions(
            account_id=selected_account,
            date_from=date_from.isoformat(),
            date_to=date_to.isoformat(),
        )
        st.write(f"Transactions: {len(txs)}")
        st.json(txs)
