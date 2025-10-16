import os
import time
import streamlit as st
import pandas as pd
from dotenv import load_dotenv
from jira import JIRA
import google.generativeai as genai
from main import parse_markdown_table, clean_html_br_tags_and_strip

# --- Load .env only when not running on Streamlit Cloud ---
if not os.environ.get("STREAMLIT_RUNTIME"):
    load_dotenv()

# --- Constants ---
OUTPUT_DIR = os.path.join(os.getcwd(), "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

FILENAME = "jira_test_cases.xlsx"
MAX_RETRIES = 3
RETRY_DELAY = 5

# --- Environment Variables ---
JIRA_EMAIL = os.getenv("JIRA_EMAIL")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")
JIRA_SERVER = os.getenv("JIRA_SERVER")
PROJECT_KEY = os.getenv("PROJECT_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# --- Check missing secrets before proceeding ---
required_keys = [
    "JIRA_EMAIL",
    "JIRA_API_TOKEN",
    "JIRA_SERVER",
    "PROJECT_KEY",
    "GEMINI_MODEL",
    "GEMINI_API_KEY",
]
missing = [k for k in required_keys if not os.getenv(k)]
if missing:
    st.error(f"❌ Missing environment variables: {', '.join(missing)}. Please add them to Streamlit Secrets.")
    st.stop()

# --- Configure Gemini ---
try:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(GEMINI_MODEL)
except Exception as e:
    st.error(f"⚠️ Failed to initialize Gemini model: {e}")
    st.stop()

# --- Streamlit UI ---
st.title("🤖 JIRA AI Test Case Generator")

st.markdown(
    """
    ### 📋 Instructions
    1. Select your JIRA project below.
    2. Choose one or more user stories from that project.
    3. Customize generation options in the sidebar.
    4. Click **Generate Test Cases** to create AI-powered test cases.
    """
)

# --- JIRA Connection ---
try:
    jira = JIRA(server=JIRA_SERVER, basic_auth=(JIRA_EMAIL, JIRA_API_TOKEN))
    all_projects = jira.projects()
    project_keys = [p.key for p in all_projects]
except Exception as e:
    st.error(f"⚠️ Jira connection failed: {e}")
    st.stop()

# --- Project Selection ---
st.subheader("📁 Select JIRA Project")
selected_project = st.selectbox(
    "Choose a project to view its user stories:",
    options=project_keys,
    index=project_keys.index(PROJECT_KEY) if PROJECT_KEY in project_keys else 0
)

@st.cache_data(show_spinner=False)
def fetch_stories(_jira_client, project_key):
    """Fetch up to 50 latest user stories from a JIRA project."""
    return _jira_client.search_issues(
        f'project={project_key} AND issuetype=Story ORDER BY created DESC',
        maxResults=50
    )


# --- Load Stories ---
issues = []
if selected_project:
    try:
        issues = fetch_stories(jira, selected_project)
        if not issues:
            st.warning(f"No user stories found in project **{selected_project}**.")
        else:
            st.success(f"✅ Loaded {len(issues)} stories from **{selected_project}**.")
    except Exception as e:
        st.error(f"⚠️ Failed to load stories for {selected_project}: {e}")

story_options = [f"{issue.key}: {issue.fields.summary}" for issue in issues] if issues else []

# --- Sidebar Options ---
st.sidebar.header("⚙️ Test Case Generation Settings")
depth = st.sidebar.slider("Test case depth", 1, 5, 3)
test_types = st.sidebar.multiselect(
    "Test case types",
    ["Functional", "Security", "Performance", "Regression"],
    default=["Functional"],
)
export_format = st.sidebar.radio("Choose export format", ["Excel", "CSV"])

# --- Multiselect Stories ---
selected_story_keys = st.multiselect(
    "Select Jira User Stories",
    options=story_options,
    help="Select one or more stories for which you want to generate test cases.",
)

# --- Helper Functions ---
def generate_test_cases(prompt_text):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = model.generate_content(prompt_text)
            return response.text
        except Exception as e:
            if attempt < MAX_RETRIES:
                st.warning(f"⚠️ Retry {attempt}/{MAX_RETRIES} due to error: {e}")
                time.sleep(RETRY_DELAY)
    return ""

def generate_all_test_cases(selected_issues):
    all_rows = []
    test_type_str = ", ".join(test_types) if test_types else "Functional"

    progress_bar = st.progress(0)
    total = len(selected_issues)

    for i, issue in enumerate(selected_issues, 1):
        story_summary = issue.fields.summary
        story_description = issue.fields.description or "No description provided."

        st.info(f"🧩 Generating test cases for **{issue.key}** — {story_summary}")

        prompt = f"""
You are a highly skilled QA engineer. Given the following Jira user story, generate detailed {test_type_str} test cases with depth {depth} and format them in a Markdown table.
Each test case should cover unique scenarios (positive and negative) with preconditions, clear multi-step steps, and explicit expected results.

Jira Story Summary: {story_summary}
Jira Description: {story_description}

Output only a Markdown table with columns:
| Test Case ID | Test Scenario | Preconditions | Steps | Expected Result | Priority |
"""

        test_table_md = generate_test_cases(prompt)
        case_rows = parse_markdown_table(test_table_md)

        for row in case_rows:
            row["Jira ID"] = issue.key
            row["Story Summary"] = story_summary
            all_rows.append(row)

        progress_bar.progress(i / total)

    progress_bar.empty()
    return all_rows

# --- Generate Button ---
if st.button("🚀 Generate Test Cases"):
    if not selected_story_keys:
        st.warning("Please select at least one user story.")
    else:
        selected_issues = [issues[story_options.index(k)] for k in selected_story_keys]

        with st.spinner("🧠 Generating test cases... please wait..."):
            test_cases = generate_all_test_cases(selected_issues)

        if test_cases:
            for row in test_cases:
                for key, value in row.items():
                    if isinstance(value, str):
                        row[key] = clean_html_br_tags_and_strip(value)

            df = pd.DataFrame(test_cases)
            st.success("✅ Test cases generated successfully!")
            st.dataframe(df, use_container_width=True)

            # --- Download options ---
            if export_format == "Excel":
                excel_path = os.path.join(OUTPUT_DIR, FILENAME)
                df.to_excel(excel_path, index=False)
                with open(excel_path, "rb") as f:
                    st.download_button(
                        label="⬇️ Download Excel",
                        data=f,
                        file_name=FILENAME,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
            else:
                csv_data = df.to_csv(index=False)
                st.download_button(
                    label="⬇️ Download CSV",
                    data=csv_data,
                    file_name="jira_test_cases.csv",
                    mime="text/csv",
                )
        else:
            st.warning("⚠️ No test cases generated. Try again.")
