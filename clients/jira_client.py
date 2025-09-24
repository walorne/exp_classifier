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

def get_field_value(field_value):
    """
    Безопасное получение значения поля JIRA
    Возвращает "-" если поле отсутствует или равно None
    """
    if field_value is None:
        return "-"
    return str(field_value)


def safe_get_custom_field(issue_fields, field_name):
    """
    Безопасное получение custom field из issue.fields
    Использует getattr с дефолтным значением None
    """
    return getattr(issue_fields, field_name, None)