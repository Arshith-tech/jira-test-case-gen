import pandas as pd
from datetime import datetime
from jira import JIRA
import google.generativeai as genai
import os
import time
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configuration from environment variables
JIRA_EMAIL = os.environ.get("JIRA_EMAIL")
JIRA_API_TOKEN = os.environ.get("JIRA_API_TOKEN")
JIRA_SERVER = os.environ.get("JIRA_SERVER")
PROJECT_KEY = os.environ.get("PROJECT_KEY")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds

OUTPUT_DIR = "output"
FILENAME = "jira_test_cases.xlsx"

# Connect to Jira
jira = JIRA(
    server=JIRA_SERVER,
    basic_auth=(JIRA_EMAIL, JIRA_API_TOKEN)
)
issues = jira.search_issues(f'project={PROJECT_KEY} AND issuetype=Story AND status="To Do"', maxResults=10)

# Initialize Gemini Pro client
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel(GEMINI_MODEL)

def generate_test_cases(prompt_text):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = model.generate_content(prompt_text)
            return response.text
        except Exception as e:
            print(f"⚠️ Attempt {attempt} failed: {e}")
            if attempt < MAX_RETRIES:
                print(f"⏳ Retrying in {RETRY_DELAY} seconds...")
                time.sleep(RETRY_DELAY)
    return ""

def parse_markdown_table(md_text):
    lines = [line.strip() for line in md_text.strip().split('\n') if '|' in line]
    if len(lines) < 2:
        return []
    headers = [h.strip() for h in lines[0].split('|') if h.strip()]
    rows = []
    for line in lines[2:]:
        fields = [f.strip() for f in line.split('|') if f.strip()]
        if len(fields) == len(headers):
            row = dict(zip(headers, fields))
            rows.append(row)
    return rows

def clean_html_br_tags_and_strip(text):
    if not text:
        return text
    return text.replace('<br>', '\n').replace('<br/>', '\n').replace('<br />', '\n').strip()

def save_to_excel(parsed_rows, filename):
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
    if parsed_rows:
        for row in parsed_rows:
            for key, value in row.items():
                if isinstance(value, str):
                    row[key] = clean_html_br_tags_and_strip(value)
        df = pd.DataFrame(parsed_rows)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        file_path = os.path.join(OUTPUT_DIR, filename.replace(".xlsx", f"_{timestamp}.xlsx"))
        df.to_excel(file_path, index=False)
        print(f"✅ Excel file created: {file_path}")
    else:
        print("⚠️ No test cases to write.")

if __name__ == "__main__":
    all_rows = []
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
        print("----------------------------------------------------")
        print(f"Issue: {issue.key} - {story_summary}")
        print("Generating test cases...")
        test_table_md = generate_test_cases(prompt)
        case_rows = parse_markdown_table(test_table_md)
        for row in case_rows:
            row["Jira ID"] = issue.key
            row["Story Summary"] = story_summary
            all_rows.append(row)
        print("✅ Generated Test Cases for:", issue.key)
        print("----------------------------------------------------\n")

    save_to_excel(all_rows, FILENAME)
    print("🎉 All done! Test cases saved in Excel.")
