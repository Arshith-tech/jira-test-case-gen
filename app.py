import streamlit as st
import pandas as pd
import os
import time
from main import generate_test_cases, parse_markdown_table, clean_html_br_tags_and_strip, save_to_excel
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

OUTPUT_DIR = "output"
FILENAME = "jira_test_cases.xlsx"

st.title("JIRA AI Test Case Generator")

def generate_all_test_cases():
    all_rows = []
    from jira import JIRA
    import google.generativeai as genai

    # Setup from environment variables
    JIRA_EMAIL = os.environ.get("JIRA_EMAIL")
    JIRA_API_TOKEN = os.environ.get("JIRA_API_TOKEN")
    JIRA_SERVER = os.environ.get("JIRA_SERVER")
    PROJECT_KEY = os.environ.get("PROJECT_KEY")
    GEMINI_MODEL = os.environ.get("GEMINI_MODEL")
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
    MAX_RETRIES = 3
    RETRY_DELAY = 5

    jira = JIRA(
        server=JIRA_SERVER,
        basic_auth=(JIRA_EMAIL, JIRA_API_TOKEN)
    )
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(GEMINI_MODEL)

    issues = jira.search_issues(f'project={PROJECT_KEY} AND issuetype=Story AND status="To Do"', maxResults=10)

    def gen(prompt_text):
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = model.generate_content(prompt_text)
                return response.text
            except Exception as e:
                time.sleep(RETRY_DELAY)
        return ""

    for issue in issues:
        story_summary = issue.fields.summary
        story_description = issue.fields.description or "No description provided."
        prompt = f'''
You are a highly skilled QA engineer. Given the following Jira user story, generate exhaustive but realistic test cases and format them in a Markdown table. 
Each test case should cover a unique scenario (positive and negative), with preconditions, clear multi-step instructions, and explicit expected results. 
Do not make up features not described.

Jira Story Summary: {story_summary}
Jira Description: {story_description}

Please output only the Markdown table with the following columns:
| Test Case ID | Test Scenario | Preconditions | Steps | Expected Result | Priority |
'''
        test_table_md = gen(prompt)
        case_rows = parse_markdown_table(test_table_md)
        for row in case_rows:
            row["Jira ID"] = issue.key
            row["Story Summary"] = story_summary
            all_rows.append(row)

    return all_rows

if st.button("Generate Test Cases"):
    with st.spinner("Generating test cases... this may take a while"):
        test_cases = generate_all_test_cases()
    if test_cases:
        # Clean HTML <br> tags
        for row in test_cases:
            for key, value in row.items():
                if isinstance(value, str):
                    row[key] = clean_html_br_tags_and_strip(value)
        df = pd.DataFrame(test_cases)
        st.dataframe(df)
        if not os.path.exists(OUTPUT_DIR):
            os.makedirs(OUTPUT_DIR)
        excel_path = os.path.join(OUTPUT_DIR, FILENAME)
        df.to_excel(excel_path, index=False)
        with open(excel_path, "rb") as f:
            st.download_button("Download Test Cases Excel", data=f, file_name=FILENAME,
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    else:
        st.warning("No test cases generated.")

