"""
Модуль для генерации категорий из задач с помощью LLM
"""
import pandas as pd
import os
from datetime import datetime
from clients.ai_client import create_default_client
from utils.file_utils import safe_save_excel


def process_batch_for_categories(batch_tasks, batch_num, total_batches, llm_client):
    """Обрабатывает батч задач для создания категорий"""
    
    # Собираем тексты для классификации
    texts_for_classification = []
    for _, row in batch_tasks.iterrows():
        text = f"Тип: {row['issuetype']}\nНазвание: {row['title']}\nОписание: {row['description']}\nСаммаризация: {row['summary']}"
        texts_for_classification.append(text)

    # Создаем промпт
    prompt = f"""Ты эксперт по анализу IT-процессов и рабочих задач. Проанализируй следующие JIRA задачи и создай категории для их классификации.

ТРЕБОВАНИЯ:
1. Создай от 3 до 8 категорий для данного батча
2. Каждая категория должна объединять логически связанные задачи
3. Названия категорий должны быть понятными и отражать суть работы
4. Избегай слишком узких или слишком широких категорий
5. Обязательно используй описание из поля "Саммаризация" - это подготовленные для классификации данные
6. Данные из остальных полей могут использоваться для более точного определения категории

ЗАДАЧИ ДЛЯ АНАЛИЗА (батч {batch_num}/{total_batches}):
{chr(10).join([f"{i+1}. {text}" for i, text in enumerate(texts_for_classification)])}

ВЕРНИ РЕЗУЛЬТАТ СТРОГО В ФОРМАТЕ CSV (разделитель - точка с запятой):
Название;Описание;Ключевые_слова;Типы_задач


ВАЖНО: 
- НЕ добавляй заголовки столбцов
- НЕ добавляй номера строк
- Каждая категория на новой строке
- Используй точку с запятой как разделитель"""
# Пример:
# API интеграции;Настройка и разработка API интеграций;api,интеграция,настройка,разработка;Task,Story
# Работа с ошибками;Исправление ошибок и багов в системе;ошибка,баг,исправление,отладка;Bug,Task

    print(f"🔄 Обрабатываю батч {batch_num}/{total_batches} ({len(batch_tasks)} задач)...")
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


def generate_categories_from_tasks(tasks_df, batch_size=50, data_folder="classification_data", save_timestamped=True):
    """
    Генерирует категории из задач батчами
    
    Args:
        tasks_df (pd.DataFrame): DataFrame с задачами
        batch_size (int): размер батча
        data_folder (str): папка для сохранения файлов
        save_timestamped (bool): сохранять ли файлы с временными метками
    
    Returns:
        pd.DataFrame: DataFrame с категориями
        str: путь к основному файлу категорий
    """
    print(f"\n🤖 Генерация категорий из {len(tasks_df)} задач...")
    
    # Создаем LLM клиент
    llm_client = create_default_client()
    
    all_categories = []

    # Разбиваем на батчи
    total_batches = (len(tasks_df) + batch_size - 1) // batch_size
    print(f"📊 Всего задач: {len(tasks_df)}")
    print(f"📦 Размер батча: {batch_size}")
    print(f"🔢 Количество батчей: {total_batches}")

    for i in range(0, len(tasks_df), batch_size):
        batch_num = (i // batch_size) + 1
        batch_tasks = tasks_df.iloc[i:i+batch_size]
        
        try:
            response = process_batch_for_categories(batch_tasks, batch_num, total_batches, llm_client)
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
    
    # Сохраняем категории с безопасной обработкой
    print(f"\n💾 Сохраняю категории в файл...")
    
    # Сохраняем основной файл категорий
    main_categories_file = os.path.join(data_folder, "categories.xlsx")
    success = safe_save_excel(categories_df, main_categories_file, 'Categories')
    
    if success:
        if save_timestamped:
            print(f"✅ Категории успешно сохранены: {main_categories_file}")
        else:
            print(f"✅ Файл успешно сохранен: {main_categories_file}")
    else:
        print(f"❌ Не удалось сохранить категории в файл: {main_categories_file}")
        return categories_df, None
    
    return categories_df, main_categories_file
