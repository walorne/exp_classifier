from jira import JIRA
from dotenv import load_dotenv
from clients.jira_client import get_jira_client
import pandas as pd
from clients.ai_client import create_default_client
import os
from datetime import datetime

JQL = "project = MPSM AND issueFunction in issuesInEpics(\"ERP_JOBs ~ '00-00377754#000000002'\") AND created >= 2025-09-01 ORDER BY created DESC"

jira = get_jira_client()

issues = jira.search_issues(JQL)

print(len(issues))

# Извлекаем нужные поля в DataFrame
data = []
for issue in issues:
    data.append({
        'key': issue.key,
        'title': issue.fields.summary,
        'description': issue.fields.description or '',
        'issuetype': issue.fields.issuetype.name,
        'time_spent': getattr(issue.fields, 'timespent', 0) or 0,
        'processing_stage': 'new',  # Этап обработки
        'category_id': '',          # ID категории (пока пустой)
        'batch_processed': 0        # Номер батча обработки
    })

df = pd.DataFrame(data)
print(df)

# Создаем папку для данных
data_folder = "classification_data"
os.makedirs(data_folder, exist_ok=True)

# Сохраняем задачи в Excel
timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
tasks_file = os.path.join(data_folder, f"tasks_{timestamp}.xlsx")
df.to_excel(tasks_file, index=False, sheet_name='Tasks')

print(f"\n✅ Сохранено {len(df)} задач в файл: {tasks_file}")

# Также сохраняем как основной файл задач
main_tasks_file = os.path.join(data_folder, "tasks.xlsx")
df.to_excel(main_tasks_file, index=False, sheet_name='Tasks')
print(f"✅ Основной файл задач: {main_tasks_file}")

# Создаем LLM клиент
llm_client = create_default_client()

# Собираем тексты для классификации
texts_for_classification = []
for _, row in df.iterrows():
    text = f"Тип: {row['issuetype']}\nНазвание: {row['title']}\nОписание: {row['description']}"
    texts_for_classification.append(text)

# Отправляем на классификацию
prompt = f"""Ты эксперт по анализу IT-процессов и рабочих задач. Проанализируй следующие JIRA задачи и создай систему категорий для их классификации.

ТРЕБОВАНИЯ:
1. Создай не более 25 категорий
2. Каждая категория должна объединять логически связанные задачи
3. Категории должны покрывать ВСЕ типы деятельности из выборки
4. Названия категорий должны быть понятными и отражать суть работы
5. Избегай слишком узких или слишком широких категорий

ЗАДАЧИ ДЛЯ АНАЛИЗА:
{chr(10).join([f"{i+1}. {text}" for i, text in enumerate(texts_for_classification)])}

ПРОАНАЛИЗИРУЙ И ОПРЕДЕЛИ:
1. Какие ТИПЫ ДЕЯТЕЛЬНОСТИ повторяются в задачах?
2. Какие ПАТТЕРНЫ можно выделить в заголовках и описаниях?
3. Как можно СГРУППИРОВАТЬ задачи по смыслу выполняемой работы?

СОЗДАЙ КАТЕГОРИИ В СЛЕДУЮЩЕМ ФОРМАТЕ:

КАТЕГОРИЯ_1:
Название: [Краткое название категории]
Описание: [Что входит в эту категорию, какие типы работ]
Ключевые_слова: [слова и фразы, которые характерны для этой категории, через запятую]
Типы_задач: [какие issue types обычно относятся к этой категории, через запятую]
Примеры: [номера задач из списка выше, которые относятся к этой категории]

КАТЕГОРИЯ_2:
...

Обязательно проанализируй ВСЕ задачи и убедись, что каждая задача может быть отнесена к одной из созданных категорий."""
print(len(prompt))
print("--------------------------------")
response = llm_client.simple_chat(prompt)
print("Классификация:")
print(response)

