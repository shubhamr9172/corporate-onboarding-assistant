import os
import uuid
import logging
import yaml
import streamlit as st
import streamlit_authenticator as stauth
from yaml.loader import SafeLoader
from dotenv import load_dotenv
from langchain_core.tracers.context import collect_runs

# Initialize logger configuration
from utils.logger_config import setup_logging

setup_logging()
logger = logging.getLogger("app.ui")

# Load environment configuration
root_dir = os.path.dirname(os.path.abspath(__file__))
dotenv_path = os.path.join(root_dir, ".env")
load_dotenv(dotenv_path=dotenv_path)

# Fast-fail configuration check on startup
from utils.config_check import check_configuration

if not check_configuration():
    st.error("Startup Configuration Failed. Please check logs for details.")
    st.stop()

# Import LangGraph compiled application
from graph.graph import create_onboarding_graph
from guardrails.guard import validate_input, validate_output
from utils.feedback import log_user_feedback
from utils.rate_limiter import is_rate_limited

# Constants
MAX_INPUT_LENGTH = 2000

# Setup Streamlit page configuration
st.set_page_config(
    page_title="Corporate Onboarding Assistant V2", page_icon="🤖", layout="wide"
)

# ==============================================================================
# AUTHENTICATION GATE (streamlit-authenticator)
# ==============================================================================

auth_config_path = os.path.join(root_dir, "auth_config.yaml")
try:
    with open(auth_config_path, "r", encoding="utf-8") as f:
        auth_config = yaml.load(f, Loader=SafeLoader)
except FileNotFoundError:
    st.error("Authentication configuration file not found. Contact your administrator.")
    st.stop()

cookie_key = os.getenv(
    "AUTH_COOKIE_KEY", "onboardai_v2_secret_cookie_key_change_in_prod"
)

authenticator = stauth.Authenticate(
    auth_config["credentials"],
    auth_config["cookie"]["name"],
    cookie_key,
    auth_config["cookie"]["expiry_days"],
)
authenticator.login(location="main", key="login_main")
authentication_status = st.session_state.get("authentication_status")
username = st.session_state.get("username")
name = st.session_state.get("name")

if authentication_status is False:
    st.error("Invalid username or password.")
    st.stop()
elif authentication_status is None:
    st.info("Please enter your username and password to access OnboardAI.")
    st.stop()

# User is authenticated from this point onward
logger.info(f"Authenticated user: {username} ({name})")

# ==============================================================================
# LOAD GRADIENT AURORA THEME
# ==============================================================================


def load_aurora_theme():
    """Load the Gradient Aurora CSS theme from styles directory."""
    css_path = os.path.join(os.path.dirname(__file__), "styles", "aurora_theme.css")
    try:
        with open(css_path, "r", encoding="utf-8") as f:
            css = f.read()
        st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
    except FileNotFoundError:
        logger.warning(
            "Aurora theme CSS not found — falling back to default Streamlit theme."
        )


load_aurora_theme()


# Load graph application once
@st.cache_resource
def get_graph():
    return create_onboarding_graph()


app = get_graph()

# ==============================================================================
# SESSION STATE INITIALIZATION
# ==============================================================================

if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if "user_role" not in st.session_state:
    st.session_state.user_role = "joinee"
if "messages" not in st.session_state:
    st.session_state.messages = []
if "topics_covered" not in st.session_state:
    st.session_state.topics_covered = {
        "Policy": False,
        "Benefits": False,
        "IT Setup": False,
        "Team": False,
        "Payroll": False,
    }
if "token_usage" not in st.session_state:
    st.session_state.token_usage = {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_cost_usd": 0.0,
    }
if "feedback_submitted" not in st.session_state:
    st.session_state.feedback_submitted = set()

# ==============================================================================
# HELPER: COMPUTE PROGRESS
# ==============================================================================


def _compute_progress():
    """Return (completed_count, total_count, percentage)."""
    topics = st.session_state.topics_covered
    done = sum(1 for v in topics.values() if v)
    total = len(topics)
    pct = int((done / total) * 100) if total else 0
    return done, total, pct


# ==============================================================================
# SIDEBAR — GRADIENT AURORA EDITION
# ==============================================================================

# Topic display names and Material Symbols icons for the step tracker
TOPIC_META = {
    "Policy": ("Policies", "policy"),
    "Benefits": ("Benefits", "card_giftcard"),
    "IT Setup": ("IT Setup", "laptop_mac"),
    "Team": ("Team Sync", "groups"),
    "Payroll": ("Payroll", "payments"),
}

with st.sidebar:
    # ── Brand Header ──
    st.markdown(
        """<div class="aurora-brand">
    <div class="aurora-logo">
        <span class="material-symbols-outlined material-filled" style="color: white; font-size: 1.25rem;">waves</span>
    </div>
    <div>
        <div class="aurora-brand-name">OnboardAI</div>
        <div class="aurora-brand-sub">Corporate Assistant</div>
    </div>
</div>""",
        unsafe_allow_html=True,
    )

    # ── User Card ──
    role_display = st.session_state.user_role.capitalize()
    initials = role_display[0].upper()
    st.markdown(
        f"""<div class="aurora-user-card">
    <div class="aurora-avatar">{initials}</div>
    <div class="aurora-user-info">
        <span class="aurora-user-name">New Hire</span>
        <span class="aurora-role-badge">{role_display}</span>
    </div>
</div>""",
        unsafe_allow_html=True,
    )

    # ── Role selector (functional) ──
    selected_role = st.selectbox(
        "Switch Role",
        options=["joinee", "manager", "HR"],
        index=["joinee", "manager", "HR"].index(st.session_state.user_role),
        label_visibility="collapsed",
    )
    if selected_role != st.session_state.user_role:
        st.session_state.user_role = selected_role
        st.rerun()

    # ── Journey Progress (inside glass profile card) ──
    done, total, pct = _compute_progress()

    # Determine the first incomplete topic as "current"
    first_incomplete = None
    for key, completed in st.session_state.topics_covered.items():
        if not completed and first_incomplete is None:
            first_incomplete = key

    # Build nav items HTML matching Stitch sidebar nav pattern
    nav_items_html = ""
    for key, completed in st.session_state.topics_covered.items():
        label, icon_name = TOPIC_META.get(key, (key, "help"))
        if completed:
            state_cls = "done"
            status_html = '<span class="material-symbols-outlined nav-status" style="font-size: 1rem;">check_circle</span>'
            icon_style = "style=\"font-variation-settings: 'FILL' 1;\""
        elif key == first_incomplete:
            state_cls = "current"
            status_html = '<div class="pulse-dot"></div>'
            icon_style = "style=\"font-variation-settings: 'FILL' 1;\""
        else:
            state_cls = "upcoming"
            status_html = ""
            icon_style = ""

        nav_items_html += f"""<div class="aurora-nav-item {state_cls}">
    <div class="nav-left">
        <span class="material-symbols-outlined nav-icon" {icon_style}>{icon_name}</span>
        <span class="nav-label">{label}</span>
    </div>
    {status_html}
</div>"""

    st.markdown(
        f"""<div class="aurora-progress-bar-wrap" style="margin-bottom: 0.75rem;">
    <div class="aurora-progress-row">
        <span class="aurora-progress-label">Journey Progress</span>
        <span class="aurora-progress-pct">{pct}%</span>
    </div>
    <div class="aurora-progress-bar">
        <div class="aurora-progress-fill" style="width: {pct}%;"></div>
    </div>
</div>
{nav_items_html}""",
        unsafe_allow_html=True,
    )

    # ── Usage Insights ──
    total_tokens = (
        st.session_state.token_usage["input_tokens"]
        + st.session_state.token_usage["output_tokens"]
    )
    cost = st.session_state.token_usage["total_cost_usd"]

    st.markdown(
        f"""<div class="aurora-section-header" style="margin-top: 0.75rem;">
    <span class="icon">📊</span> Insights
</div>
<div class="aurora-metrics-row">
    <div class="aurora-metric-card">
        <div class="aurora-metric-label">Tokens</div>
        <div class="aurora-metric-value">{total_tokens:,}</div>
    </div>
    <div class="aurora-metric-card">
        <div class="aurora-metric-label">Cost</div>
        <div class="aurora-metric-value secondary">${cost:.5f}</div>
    </div>
</div>""",
        unsafe_allow_html=True,
    )

    # Warn user if cost approaches limits
    if cost >= 0.40:
        st.warning("⚠️ Approaching session budget limit ($0.50)!")

    # Re-index data button
    if st.button("🔄  Sync Documents", use_container_width=True):
        with st.spinner("Re-indexing documents folder..."):
            try:
                from rag.ingest import run_ingestion

                run_ingestion()
                st.success("Knowledge base refreshed!")
                st.rerun()
            except Exception as e:
                st.error(f"Re-indexing failed: {e}")

    # Reset Chat Session button
    if st.button("✨  Start Fresh", use_container_width=True):
        try:
            # Delete SQLite checkpoints for the current thread ID
            root_dir = os.path.dirname(os.path.abspath(__file__))
            db_path = os.path.join(root_dir, "onboarding_history.db")
            if os.path.exists(db_path):
                import sqlite3

                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                # Prune current thread history
                ALLOWED_TABLES = {
                    "checkpoints",
                    "checkpoint_blobs",
                    "checkpoint_writes",
                    "writes",
                }
                for t in ALLOWED_TABLES:
                    try:
                        cursor.execute(
                            f"DELETE FROM {t} WHERE thread_id = ?",
                            (st.session_state.session_id,),
                        )
                    except Exception as e:
                        logger.warning(f"Could not clear table '{t}' during reset: {e}")
                conn.commit()
                conn.close()
                logger.info(
                    f"Chat thread {st.session_state.session_id} checkpoint wiped."
                )
        except Exception as e:
            logger.error(f"Error purging checkpoints during reset: {e}")

        # Reset local Session State variables
        st.session_state.session_id = str(uuid.uuid4())
        st.session_state.messages = []
        st.session_state.topics_covered = {
            "Policy": False,
            "Benefits": False,
            "IT Setup": False,
            "Team": False,
            "Payroll": False,
        }
        st.session_state.token_usage = {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_cost_usd": 0.0,
        }
        st.session_state.feedback_submitted = set()
        st.success("Session restarted successfully!")
        st.rerun()

    # ── Session ID (footer) ──
    short_id = st.session_state.session_id[:8]
    st.markdown(
        f"""<div style="padding-top: 0.75rem;">
    <div class="aurora-session-badge">
        <div class="aurora-session-dot"></div>
        Session {short_id}
    </div>
</div>""",
        unsafe_allow_html=True,
    )

# ==============================================================================
# MAIN CHAT INTERFACE — GRADIENT AURORA EDITION
# ==============================================================================

# ── Hero Section (shown only when no messages yet) ──
if not st.session_state.messages:
    done, total, pct = _compute_progress()
    st.markdown(
        f"""<div class="aurora-hero">
    <div class="aurora-hero-greeting">Good Morning!</div>
    <div class="aurora-hero-sub">
        Your onboarding journey continues. <strong>{done} of {total}</strong> topics completed.
    </div>
</div>
<div class="aurora-suggestions">
    <div class="aurora-chip">
        <span class="aurora-chip-category">Policy</span>
        <span class="aurora-chip-text">What is the leave policy?</span>
    </div>
    <div class="aurora-chip">
        <span class="aurora-chip-category">Setup</span>
        <span class="aurora-chip-text">How do I set up VPN?</span>
    </div>
    <div class="aurora-chip">
        <span class="aurora-chip-category">Benefits</span>
        <span class="aurora-chip-text">Tell me about health insurance</span>
    </div>
</div>
<div class="aurora-footer">Powered by OnboardAI &bull; Private &amp; Secure</div>""",
        unsafe_allow_html=True,
    )
else:
    # Compact header when chat is active
    st.markdown(
        """<div class="aurora-compact-header">
    <span class="aurora-compact-title">OnboardAI</span>
</div>""",
        unsafe_allow_html=True,
    )

# ── Render Chat History ──
for idx, msg in enumerate(st.session_state.messages):
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

        # Display source citations if present
        if msg.get("sources"):
            with st.expander("📚 View Document Sources"):
                for doc in msg["sources"]:
                    st.markdown(f"**[{doc['index']}] {doc['source']}**")
                    st.caption(doc["text"])

        # Render feedback module for Assistant messages
        if msg["role"] == "assistant":
            msg_id = f"msg_{idx}"

            # Skip rendering if already voted
            if msg_id not in st.session_state.feedback_submitted:
                c1, c2, c3 = st.columns([0.05, 0.05, 0.9])
                with c1:
                    if st.button("👍", key=f"up_{msg_id}"):
                        log_user_feedback(
                            session_id=st.session_state.session_id,
                            query=st.session_state.messages[idx - 1]["content"],
                            answer=msg["content"],
                            rating=1,
                            run_id=msg.get("run_id"),
                        )
                        st.session_state.feedback_submitted.add(msg_id)
                        st.success("Thanks!")
                        st.rerun()
                with c2:
                    if st.button("👎", key=f"down_{msg_id}"):
                        st.session_state[f"show_feedback_form_{msg_id}"] = True

                # Handle text comment review box on thumbs-down
                if st.session_state.get(f"show_feedback_form_{msg_id}"):
                    with st.form(key=f"form_{msg_id}"):
                        comment = st.text_input(
                            "Help us improve. What was wrong with this answer?",
                            key=f"comment_{msg_id}",
                        )
                        submit = st.form_submit_button("Submit Feedback")
                        if submit:
                            log_user_feedback(
                                session_id=st.session_state.session_id,
                                query=st.session_state.messages[idx - 1]["content"],
                                answer=msg["content"],
                                rating=-1,
                                comment=comment,
                                run_id=msg.get("run_id"),
                            )
                            st.session_state.feedback_submitted.add(msg_id)
                            st.session_state[f"show_feedback_form_{msg_id}"] = False
                            st.success("Feedback submitted!")
                            st.rerun()

# ── Accept Chat Input ──
if prompt := st.chat_input("Ask anything about your onboarding..."):
    # 1. Add human message in UI
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # 1.0 Rate limit check
    if is_rate_limited(st.session_state.session_id):
        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": "⏳ You're sending messages too quickly. Please wait a moment before trying again.",
            }
        )
        with st.chat_message("assistant"):
            st.warning(
                "Rate limit exceeded. Please wait before sending another message."
            )

    # 1.5 Input length guard
    elif len(prompt) > MAX_INPUT_LENGTH:
        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": f"🚨 Your message exceeds the maximum length of {MAX_INPUT_LENGTH} characters. Please shorten it.",
            }
        )
        with st.chat_message("assistant"):
            st.warning(
                f"Message exceeds maximum length of {MAX_INPUT_LENGTH} characters."
            )

    else:
        # 2. Run Input Guardrails
        is_safe, reason = validate_input(
            prompt, st.session_state.token_usage["total_cost_usd"]
        )

        if not is_safe:
            st.session_state.messages.append(
                {"role": "assistant", "content": f"🚨 Safety Block: {reason}"}
            )
            with st.chat_message("assistant"):
                st.error(f"Safety Block: {reason}")
        else:
            # 3. Invoke LangGraph with run tracers
            config = {"configurable": {"thread_id": st.session_state.session_id}}

            # Prepare input dictionary for State
            graph_input = {
                "current_message": prompt,
                "user_role": st.session_state.user_role,
                "conversation_history": st.session_state.messages[
                    :-1
                ],  # Keep previous messages
                "topics_covered": st.session_state.topics_covered,
                "token_usage": st.session_state.token_usage,
            }

            with st.chat_message("assistant"):
                with st.spinner("Analyzing queries and matching policies..."):
                    try:
                        # Run within LangChain collect_runs callback context to extract run IDs
                        with collect_runs() as cb:
                            final_state = app.invoke(graph_input, config)
                            run_id = (
                                str(cb.traced_runs[0].id) if cb.traced_runs else None
                            )

                        # 4. Extract outputs
                        raw_response = final_state.get(
                            "final_response",
                            "I'm having trouble formulating a response.",
                        )
                        source_docs = final_state.get("source_docs") or []

                        # 5. Run Output Guardrails
                        is_output_safe, checked_response = validate_output(
                            raw_response, source_docs
                        )

                        if not is_output_safe:
                            checked_response = (
                                "Response blocked: System safety filter triggered."
                            )
                            source_docs = []

                        # 6. Update local session states
                        st.session_state.topics_covered = (
                            final_state.get("topics_covered")
                            or st.session_state.topics_covered
                        )
                        st.session_state.token_usage = (
                            final_state.get("token_usage")
                            or st.session_state.token_usage
                        )

                        # Store messages
                        st.session_state.messages.append(
                            {
                                "role": "assistant",
                                "content": checked_response,
                                "sources": source_docs,
                                "run_id": run_id,
                            }
                        )

                        # Force rerun to cleanly paint feedback blocks
                        st.rerun()

                    except Exception as e:
                        logger.critical(
                            f"ALERT:GRAPH_FAILURE session={st.session_state.session_id} error={e}",
                            exc_info=True,
                        )
                        st.error(
                            "I experienced a technical issue processing your request. Our team has been automatically alerted."
                        )
                        st.session_state.messages.append(
                            {
                                "role": "assistant",
                                "content": "I encountered a technical issue. Our support team has been automatically notified and will follow up.",
                            }
                        )
                        st.rerun()
