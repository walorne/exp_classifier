from jira import JIRA
import os
from dotenv import load_dotenv

load_dotenv()

def get_jira_client():
    jira_url = os.getenv("JIRA_URL")
    jira_token = os.getenv("JIRA_TOKEN")
    cert_path = os.getenv("JIRA_CERT_PATH", None)  # Новый параметр для сертификата
    verify_ssl = os.getenv("JIRA_VERIFY_SSL", "true").lower() == "true"

    options = {
        "server": jira_url,
        "timeout": 60,  # Увеличиваем таймаут до 60 секунд
        "max_retries": 3,  # Количество повторных попыток
    }
    
    if cert_path:
        options["verify"] = cert_path  # Указываем путь к сертификату
    elif not verify_ssl:
        options["verify"] = False  # Отключаем проверку SSL если указано в .env
        # Подавляем предупреждения SSL
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    jira = JIRA(options=options, token_auth=jira_token)
    return jira
