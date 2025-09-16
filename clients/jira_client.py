from jira import JIRA
import os
from dotenv import load_dotenv

load_dotenv()

def get_jira_client():
    jira_url = os.getenv("JIRA_URL")
    jira_token = os.getenv("JIRA_TOKEN")
    cert_path = os.getenv("JIRA_CERT_PATH", None)  # Новый параметр для сертификата

    options = {"server": jira_url}
    if cert_path:
        options["verify"] = cert_path  # Указываем путь к сертификату

    jira = JIRA(options=options, token_auth=jira_token)
    return jira
