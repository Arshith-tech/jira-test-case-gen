import streamlit as st
import pandas as pd
import os
import time
from dotenv import load_dotenv
from jira import JIRA
import google.generativeai as genai
from main import parse_markdown_table, clean_html_br_tags_and_strip

load_dotenv()

OUTPUT_DIR = "output"
FILENAME = "jira_test_cases.xlsx"

JIRA_EMAIL = os.getenv("JIRA_EMAIL")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")
JIRA_SERVER = os.getenv("JIRA_SERVER")
PROJECT_KEY = os.getenv("PROJECT_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

MAX_RETRIES = 3
RETRY_DELAY = 5

st.title("JIRA AI Test Case Generator")

st.markdown(
    """
    ### Instructions
    - Select Jira user stories from the list below.
    - Use the options in the sidebar to customize test case generation.
    - Click "Generate Test Cases" to begin.
    - Results will appear below with an option to download.
    """
)

jira = JIRA(server=JIRA_SERVER, basic_auth=(JIRA_EMAIL, JIRA_API_TOKEN))
issues = jira.search_issues(f'project={PROJECT_KEY} AND issuetype=Story AND status="To Do"', maxResults=50)

story_options = [f"{issue.key}: {issue.fields.summary}" for issue in issues]

selected_story_keys = st.multiselect(
    "Select Jira User Stories",
    options=story_options,
    help="Select one or more stories for which you want to generate test cases."
)

st.sidebar.header("Test Case Generation Options")

depth = st.sidebar.slider("Test case depth", min_value=1, max_value=5, value=3, help="Controls the detail level of generated test cases.")
test_types = st.sidebar.multiselect("Test case types", ["Functional", "Security", "Performance", "Regression"], default=["Functional"], help="Select one or more categories for generated test cases.")
export_format = st.sidebar.radio("Choose export format", ["Excel", "CSV"])

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel(GEMINI_MODEL)

def generate_test_cases(prompt_text):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = model.generate_content(prompt_text)
            return response.text
        except Exception as e:
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)
    return ""

def generate_all_test_cases(selected_issues):
    all_rows = []
    test_type_str = ", ".join(test_types) if test_types else "Functional"

    for issue in selected_issues:
        story_summary = issue.fields.summary
        story_description = issue.fields.description or "No description provided."
        prompt = f'''
You are a highly skilled QA engineer. Given the following Jira user story, generate detailed {test_type_str} test cases with depth {depth} and format them in a Markdown table. 
Each test case should cover a unique scenario (positive and negative), with preconditions, clear multi-step instructions, and explicit expected results. 
Do not make up features not described.

Jira Story Summary: {story_summary}
Jira Description: {story_description}

Please output only the Markdown table with the following columns:
| Test Case ID | Test Scenario | Preconditions | Steps | Expected Result | Priority |
'''
        st.write(f"Generating test cases for {issue.key}...")
        test_table_md = generate_test_cases(prompt)
        case_rows = parse_markdown_table(test_table_md)
        for row in case_rows:
            row["Jira ID"] = issue.key
            row["Story Summary"] = story_summary
            all_rows.append(row)

    return all_rows

if st.button("Generate Test Cases"):
    if not selected_story_keys:
        st.warning("Please select at least one user story.")
    else:
        selected_issues = [issues[story_options.index(key)] for key in selected_story_keys]

        with st.spinner("Generating test cases... this may take a while"):
            test_cases = generate_all_test_cases(selected_issues)

        if test_cases:
            for row in test_cases:
                for key, value in row.items():
                    if isinstance(value, str):
                        row[key] = clean_html_br_tags_and_strip(value)

            df = pd.DataFrame(test_cases)
            st.dataframe(df)

            if not os.path.exists(OUTPUT_DIR):
                os.makedirs(OUTPUT_DIR)

            if export_format == "Excel":
                excel_path = os.path.join(OUTPUT_DIR, FILENAME)
                df.to_excel(excel_path, index=False)
                with open(excel_path, "rb") as f:
                    st.download_button(
                        "Download Test Cases Excel",
                        data=f,
                        file_name=FILENAME,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
            else:
                csv_data = df.to_csv(index=False)
                st.download_button(
                    "Download Test Cases CSV",
                    data=csv_data,
                    file_name="jira_test_cases.csv",
                    mime="text/csv"
                )
        else:
            st.warning("No test cases generated.")
