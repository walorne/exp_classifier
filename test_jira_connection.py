"""
Тестовый скрипт для проверки подключения к JIRA
"""
from clients.jira_client import get_jira_client
from dotenv import load_dotenv
import os

load_dotenv()

try:
    print("🔍 Тестирую подключение к JIRA...")
    print(f"URL: {os.getenv('JIRA_URL')}")
    print(f"Токен: {os.getenv('JIRA_TOKEN')[:10]}..." if os.getenv('JIRA_TOKEN') else "Токен не найден")
    
    jira = get_jira_client()
    
    # Тестовый запрос - получить информацию о текущем пользователе
    user = jira.current_user()
    print(f"✅ Подключение успешно! Пользователь: {user}")
    
    # Тестовый поиск с минимальным количеством результатов
    test_jql = "project = OSTINAPP AND issuekey = OSTINAPP-14432"
    issues = jira.search_issues(test_jql, maxResults=1)
    issues = jira.search_issues(
                    test_jql, 
                    fields='key,summary,description,issuetype,timespent,comment'  # 🔥 ТОЛЬКО НУЖНЫЕ ПОЛЯ + КОММЕНТАРИИ
                )
    print(f"✅ Тестовый поиск успешен! Найдено задач: {len(issues)}")
    
    if issues:
        issue = issues[0]
        print(f"   Пример задачи: {issue.key} - {issue.fields.summary}- {issue.fields.timespent/3600}")
        
except Exception as e:
    print(f"❌ Ошибка подключения: {e}")
    print("\n🔧 Возможные решения:")
    print("1. Создайте новый Personal Access Token в JIRA")
    print("2. Проверьте URL JIRA в .env файле")
    print("3. Убедитесь, что токен имеет права на чтение проектов")
