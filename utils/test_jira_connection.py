"""
Тестовый скрипт для проверки подключения к JIRA
"""
from clients.jira_client import get_jira_client
from dotenv import load_dotenv
import os

load_dotenv()

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

try:
    print("🔍 Тестирую подключение к JIRA...")
    print(f"URL: {os.getenv('JIRA_URL')}")
    print(f"Токен: {os.getenv('JIRA_TOKEN')[:10]}..." if os.getenv('JIRA_TOKEN') else "Токен не найден")
    
    jira = get_jira_client()
    
    # Тестовый запрос - получить информацию о текущем пользователе
    user = jira.current_user()
    print(f"✅ Подключение успешно! Пользователь: {user}")
    
    # Тестовый поиск с минимальным количеством результатов
    test_jql = "issuekey = DSAC-2267"
    # test_jql = "issuekey = MPSM-18710"
    issues = jira.search_issues(test_jql, maxResults=1)
    issues = jira.search_issues(
                    test_jql, 
                    fields='key,summary,description,issuetype,timespent,comment,customfield_19003,customfield_12407,customfield_20703'  # 🔥 ТОЛЬКО НУЖНЫЕ ПОЛЯ + КОММЕНТАРИИ
                )
    print(f"✅ Тестовый поиск успешен! Найдено задач: {len(issues)}")
    
    if issues:
        issue = issues[0]
        # Безопасное получение значений полей с использованием вспомогательной функции
        cf_19003 = get_field_value(safe_get_custom_field(issue.fields, 'customfield_19003'))
        cf_12407 = get_field_value(safe_get_custom_field(issue.fields, 'customfield_12407'))
        cf_20703 = get_field_value(safe_get_custom_field(issue.fields, 'customfield_20703'))
        timespent = get_field_value(safe_get_custom_field(issue.fields, 'timespent'))

        print(f"   Пример задачи: {issue.key} - {issue.fields.summary} - {cf_19003} - {cf_12407} - {cf_20703} - {timespent}")

        # Подробная отладочная информация
        print("   📊 Подробная информация о полях:")
        print(f"      customfield_19003: {cf_19003} (тип: {type(getattr(issue.fields, 'customfield_19003', 'Поле отсутствует'))})")
        print(f"      customfield_12407: {cf_12407} (тип: {type(getattr(issue.fields, 'customfield_12407', 'Поле отсутствует'))})")
        print(f"      customfield_20703: {cf_20703} (тип: {type(getattr(issue.fields, 'customfield_20703', 'Поле отсутствует'))})")
        print(f"      timespent: {timespent} (тип: {type(getattr(issue.fields, 'timespent', 'Поле отсутствует'))})")

except Exception as e:
    print(f"❌ Ошибка: {e}")
    print(f"   Тип ошибки: {type(e).__name__}")
    print("\n🔧 Возможные решения:")
    print("1. Создайте новый Personal Access Token в JIRA")
    print("2. Проверьте URL JIRA в .env файле")
    print("3. Убедитесь, что токен имеет права на чтение проектов")
    print("4. Проверьте, что указанная задача существует и доступна")
    print("5. Проверьте, что custom fields (19003, 12407, 20703) существуют в вашем проекте")
