from jira import JIRA
from dotenv import load_dotenv
from clients.jira_client import get_jira_client
import pandas as pd
from clients.ai_client import create_default_client
import os
from datetime import datetime
import re

# Конфигурация скрипта
JQL = "project = MPSM AND issueFunction in issuesInEpics(\"ERP_JOBs ~ '00-00377754#000000002'\") AND created >= 2025-08-01 ORDER BY created DESC"
CATEGORY_FINAL_COUNT = 10

jira = get_jira_client()

issues = jira.search_issues(JQL, maxResults=False)  # Получить до 1000 результатов

print(len(issues))

def clean_description(desc):
    """Очистка описания от лишних символов и форматирования"""
    if not desc:
        return ''
    
    # Удаляем переносы строк и лишние пробелы
    desc = desc.replace('\n', ' ').replace('\r', ' ')
    desc = ' '.join(desc.split())  # Убираем множественные пробелы
    
    # Удаляем JIRA разметку
    desc = re.sub(r'\{[^}]*\}', '', desc)  # {code}, {quote}, etc.
    desc = re.sub(r'\[[^\]]*\]', '', desc)  # [~username], [link]
    desc = re.sub(r'h[1-6]\.\s*', '', desc)  # h1. h2. заголовки
    desc = re.sub(r'\*[^*]*\*', '', desc)  # *жирный текст*
    desc = re.sub(r'_[^_]*_', '', desc)  # _курсив_
    
    # Убираем URL
    desc = re.sub(r'https?://\S+', '', desc)
    
    # Убираем лишние символы
    desc = re.sub(r'[^\w\s\-.,!?()]', ' ', desc, flags=re.UNICODE)
    
    # Финальная очистка пробелов
    desc = ' '.join(desc.split())
    
    return desc

# Извлекаем нужные поля в DataFrame
data = []
for issue in issues:
    data.append({
        'key': issue.key,
        'title': issue.fields.summary,
        'description': clean_description(issue.fields.description),
        'issuetype': issue.fields.issuetype.name,
        'time_spent': getattr(issue.fields, 'timespent', 0) or 0,
        'processing_stage': 'new',  # Этап обработки
        'category_id': '',          # ID категории (пока пустой)
        'batch_processed': 0        # Номер батча обработки
    })

df = pd.DataFrame(data)
# print(df)

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

def process_batch_for_categories(batch_tasks, batch_num, total_batches):
    """Обрабатывает батч задач для создания категорий"""
    
    # Собираем тексты для классификации
    texts_for_classification = []
    for _, row in batch_tasks.iterrows():
        text = f"Тип: {row['issuetype']}\nНазвание: {row['title']}\nОписание: {row['description']}"
        texts_for_classification.append(text)

    # Создаем промпт
    prompt = f"""Ты эксперт по анализу IT-процессов и рабочих задач. Проанализируй следующие JIRA задачи и создай категории для их классификации.

ТРЕБОВАНИЯ:
1. Создай от 3 до 8 категорий для данного батча
2. Каждая категория должна объединять логически связанные задачи
3. Названия категорий должны быть понятными и отражать суть работы
4. Избегай слишком узких или слишком широких категорий

ЗАДАЧИ ДЛЯ АНАЛИЗА (батч {batch_num}/{total_batches}):
{chr(10).join([f"{i+1}. {text}" for i, text in enumerate(texts_for_classification)])}

ВЕРНИ РЕЗУЛЬТАТ СТРОГО В ФОРМАТЕ CSV (разделитель - точка с запятой):
Название;Описание;Ключевые_слова;Типы_задач

Пример:
API интеграции;Настройка и разработка API интеграций;api,интеграция,настройка,разработка;Task,Story
Работа с ошибками;Исправление ошибок и багов в системе;ошибка,баг,исправление,отладка;Bug,Task

ВАЖНО: 
- НЕ добавляй заголовки столбцов
- НЕ добавляй номера строк
- Каждая категория на новой строке
- Используй точку с запятой как разделитель"""

    print(f"\n🔄 Обрабатываю батч {batch_num}/{total_batches} ({len(batch_tasks)} задач)...")
    response = llm_client.simple_chat(prompt)
    return response

def parse_categories_response(response_text):
    """Парсит ответ модели и возвращает список категорий"""
    categories = []
    lines = response_text.strip().split('\n')
    
    for line in lines:
        line = line.strip()
        if not line or line.startswith('Название') or line.startswith('#'):
            continue
            
        parts = line.split(';')
        if len(parts) >= 4:
            categories.append({
                'Название': parts[0].strip(),
                'Описание': parts[1].strip(),
                'Ключевые_слова': parts[2].strip(),
                'Типы_задач': parts[3].strip()
            })
    
    return categories

# Батчевая обработка для создания категорий
batch_size = 50
all_categories = []

# Разбиваем на батчи
total_batches = (len(df) + batch_size - 1) // batch_size
print(f"\n📊 Всего задач: {len(df)}")
print(f"📦 Размер батча: {batch_size}")
print(f"🔢 Количество батчей: {total_batches}")

for i in range(0, len(df), batch_size):
    batch_num = (i // batch_size) + 1
    batch_tasks = df.iloc[i:i+batch_size]
    
    try:
        response = process_batch_for_categories(batch_tasks, batch_num, total_batches)
        batch_categories = parse_categories_response(response)
        
        print(f"✅ Батч {batch_num}: получено {len(batch_categories)} категорий")
        all_categories.extend(batch_categories)
        
    except Exception as e:
        print(f"❌ Ошибка в батче {batch_num}: {e}")
        continue

# Создаем DataFrame с категориями
categories_df = pd.DataFrame(all_categories)

# Убираем дубликаты по названию (оставляем первое вхождение)
categories_df = categories_df.drop_duplicates(subset=['Название'], keep='first')

print(f"\n📋 Всего создано категорий: {len(categories_df)}")
print(categories_df)

# Сохраняем категории в Excel
categories_file = os.path.join(data_folder, f"categories_{timestamp}.xlsx")
categories_df.to_excel(categories_file, index=False, sheet_name='Categories')

print(f"\n✅ Категории сохранены в файл: {categories_file}")

# Также сохраняем как основной файл категорий
main_categories_file = os.path.join(data_folder, "categories.xlsx")
categories_df.to_excel(main_categories_file, index=False, sheet_name='Categories')
print(f"✅ Основной файл категорий: {main_categories_file}")

def consolidate_categories(categories_df, target_count=CATEGORY_FINAL_COUNT):
    """Консолидирует категории до целевого количества"""
    
    # Подготавливаем данные для модели
    categories_text = ""
    for idx, row in categories_df.iterrows():
        categories_text += f"{idx+1}. {row['Название']}: {row['Описание']}\n"
    
    prompt = f"""Ты эксперт по анализации и структурированию данных. У тебя есть список категорий для классификации IT-задач.

ТВОЯ ЗАДАЧА:
1. Проанализируй все категории и найди похожие по смыслу
2. Объедини похожие категории в одну
3. Создай ровно {target_count} итоговых категорий
4. НЕЛЬЗЯ удалять категории - только объединять!

ИСХОДНЫЕ КАТЕГОРИИ:
{categories_text}

ПРАВИЛА ОБЪЕДИНЕНИЯ:
- Название новой категории должно отражать суть ВСЕХ объединенных категорий
- Описание должно включать все аспекты объединенных категорий
- Если категории нельзя объединить - оставь их как есть
- Результат должен содержать ровно {target_count} категорий

ВЕРНИ РЕЗУЛЬТАТ СТРОГО В ФОРМАТЕ CSV (разделитель - точка с запятой):
Название;Описание

Пример:
API и интеграции;Разработка, настройка и поддержка API интеграций, веб-сервисов и внешних подключений
Исправление ошибок и багов;Анализ, диагностика и устранение ошибок в системе, отладка и тестирование исправлений

ВАЖНО:
- НЕ добавляй заголовки столбцов
- НЕ добавляй номера строк  
- Каждая категория на новой строке
- Используй точку с запятой как разделитель
- Ровно {target_count} строк в ответе"""

    print(f"\n🔄 Консолидирую {len(categories_df)} категорий в {target_count}...")
    response = llm_client.simple_chat(prompt)
    return response

def parse_consolidated_categories(response_text):
    """Парсит консолидированные категории"""
    categories = []
    lines = response_text.strip().split('\n')
    
    for line in lines:
        line = line.strip()
        if not line or line.startswith('Название') or line.startswith('#'):
            continue
            
        parts = line.split(';')
        if len(parts) >= 2:
            categories.append({
                'Название': parts[0].strip(),
                'Описание': parts[1].strip()
            })
    
    return categories

# Консолидация категорий
if len(categories_df) > 10:
    print(f"\n📊 Консолидация: {len(categories_df)} → 10 категорий")
    
    try:
        consolidated_response = consolidate_categories(categories_df, target_count=10)
        consolidated_categories = parse_consolidated_categories(consolidated_response)
        
        if len(consolidated_categories) == 10:
            # Создаем DataFrame с консолидированными категориями
            final_categories_df = pd.DataFrame(consolidated_categories)
            
            print(f"✅ Консолидация завершена: {len(final_categories_df)} категорий")
            print("\n📋 ИТОГОВЫЕ КАТЕГОРИИ:")
            for idx, row in final_categories_df.iterrows():
                print(f"{idx+1}. {row['Название']}")
            
            # Сохраняем консолидированные категории
            final_categories_file = os.path.join(data_folder, f"final_categories_{timestamp}.xlsx")
            final_categories_df.to_excel(final_categories_file, index=False, sheet_name='Final_Categories')
            
            # Основной файл итоговых категорий
            main_final_file = os.path.join(data_folder, "final_categories.xlsx")
            final_categories_df.to_excel(main_final_file, index=False, sheet_name='Final_Categories')
            
            print(f"\n✅ Итоговые категории сохранены:")
            print(f"   📄 {final_categories_file}")
            print(f"   📄 {main_final_file}")
            
        else:
            print(f"⚠️ Получено {len(consolidated_categories)} категорий вместо 10")
            print("Используем исходные категории")
            
    except Exception as e:
        print(f"❌ Ошибка при консолидации: {e}")
        print("Используем исходные категории")
else:
    print(f"\n✅ Категорий уже {len(categories_df)} - консолидация не требуется")

