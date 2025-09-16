"""
Модуль для присвоения финальных категорий JIRA задачам
"""
import pandas as pd
import os
import re
from datetime import datetime
from clients.ai_client import create_default_client


def load_tasks_and_categories(data_folder="classification_data"):
    """Загружает задачи и финальные категории из Excel файлов"""
    
    tasks_file = os.path.join(data_folder, "tasks.xlsx")
    categories_file = os.path.join(data_folder, "final_categories.xlsx")
    
    if not os.path.exists(tasks_file):
        raise FileNotFoundError(f"Файл задач не найден: {tasks_file}")
    
    if not os.path.exists(categories_file):
        raise FileNotFoundError(f"Файл категорий не найден: {categories_file}")
    
    tasks_df = pd.read_excel(tasks_file)
    categories_df = pd.read_excel(categories_file)
    
    print(f"📋 Загружено задач: {len(tasks_df)}")
    print(f"🏷️ Загружено категорий: {len(categories_df)}")
    
    return tasks_df, categories_df


def classify_tasks_with_llm(tasks_batch, categories_df, batch_num, total_batches, llm_client):
    """Классифицирует батч задач с помощью LLM"""
    
    # Подготавливаем список категорий для промпта
    categories_text = ""
    for idx, row in categories_df.iterrows():
        categories_text += f"{idx+1}. {row['Название']}: {row['Описание']}\n"
    
    # Подготавливаем задачи для классификации
    tasks_text = ""
    for idx, (_, row) in enumerate(tasks_batch.iterrows()):
        tasks_text += f"{idx+1}. [{row['key']}] {row['title']}\n"
        if row['description']:
            # Обрезаем описание для экономии токенов
            desc = row['description']
            tasks_text += f"   Описание: {desc}\n"
        tasks_text += f"   Тип: {row['issuetype']}\n\n"
    
    prompt = f"""Ты эксперт по классификации IT-задач. Определи к какой категории относится каждая задача.

ДОСТУПНЫЕ КАТЕГОРИИ:
{categories_text}

ЗАДАЧИ ДЛЯ КЛАССИФИКАЦИИ (батч {batch_num}/{total_batches}):
{tasks_text}

ТРЕБОВАНИЯ:
1. Для каждой задачи выбери ОДНУ наиболее подходящую категорию
2. Используй номер категории (1, 2, 3, ...)
3. Если задача не подходит ни к одной категории, выбери наиболее близкую

ВЕРНИ РЕЗУЛЬТАТ В ФОРМАТЕ:
1;3
2;1
3;7
...

ГДЕ:
- Первое число = номер задачи в батче
- Второе число = номер выбранной категории

ВАЖНО:
- Только цифры и точки с запятой
- Каждая задача на новой строке
- {len(tasks_batch)} строк в ответе"""

    print(f"🤖 Классифицирую батч {batch_num}/{total_batches} ({len(tasks_batch)} задач)...")
    response = llm_client.simple_chat(prompt)
    return response


def parse_classification_response(response_text, tasks_batch, categories_df):
    """Парсит ответ LLM и возвращает результаты классификации"""
    
    results = []
    lines = response_text.strip().split('\n')
    
    # Создаем список названий категорий для быстрого доступа
    category_names = categories_df['Название'].tolist()
    
    for line in lines:
        line = line.strip()
        if not line or ';' not in line:
            continue
            
        try:
            parts = line.split(';')
            if len(parts) >= 2:
                task_idx = int(parts[0]) - 1  # Индекс задачи (начинаем с 0)
                category_idx = int(parts[1]) - 1  # Индекс категории (начинаем с 0)
                
                # Проверяем корректность индексов
                if 0 <= task_idx < len(tasks_batch) and 0 <= category_idx < len(categories_df):
                    task_row = tasks_batch.iloc[task_idx]
                    category_name = category_names[category_idx]
                    
                    results.append({
                        'key': task_row['key'],
                        'category': category_name,
                        'category_id': category_idx + 1
                    })
                    
        except (ValueError, IndexError) as e:
            print(f"⚠️ Ошибка парсинга строки '{line}': {e}")
            continue
    
    return results


def classify_all_tasks(tasks_df, categories_df, batch_size=20, data_folder="classification_data"):
    """
    Классифицирует все задачи по финальным категориям
    
    Args:
        tasks_df (pd.DataFrame): DataFrame с задачами
        categories_df (pd.DataFrame): DataFrame с финальными категориями
        batch_size (int): размер батча для LLM (по умолчанию 20)
        data_folder (str): папка для сохранения файлов
    
    Returns:
        pd.DataFrame: DataFrame с классифицированными задачами
        str: путь к файлу с результатами
    """
    print(f"\n🎯 Классификация {len(tasks_df)} задач по {len(categories_df)} категориям...")
    
    # Создаем LLM клиент
    llm_client = create_default_client()
    
    # Копируем исходный DataFrame
    classified_df = tasks_df.copy()
    classified_df['assigned_category'] = ''
    classified_df['category_id'] = 0
    classified_df['classification_confidence'] = 'llm'
    
    all_classifications = []
    
    # Разбиваем на батчи
    total_batches = (len(tasks_df) + batch_size - 1) // batch_size
    print(f"📦 Размер батча: {batch_size}")
    print(f"🔢 Количество батчей: {total_batches}")
    
    for i in range(0, len(tasks_df), batch_size):
        batch_num = (i // batch_size) + 1
        tasks_batch = tasks_df.iloc[i:i+batch_size]
        
        try:
            # Классифицируем батч
            response = classify_tasks_with_llm(
                tasks_batch, categories_df, batch_num, total_batches, llm_client
            )
            
            # Парсим результат
            batch_results = parse_classification_response(response, tasks_batch, categories_df)
            
            print(f"✅ Батч {batch_num}: классифицировано {len(batch_results)}/{len(tasks_batch)} задач")
            
            # Добавляем результаты
            all_classifications.extend(batch_results)
            
        except Exception as e:
            print(f"❌ Ошибка в батче {batch_num}: {e}")
            continue
    
    # Применяем результаты классификации к DataFrame
    for result in all_classifications:
        mask = classified_df['key'] == result['key']
        classified_df.loc[mask, 'assigned_category'] = result['category']
        classified_df.loc[mask, 'category_id'] = result['category_id']
    
    # Подсчитываем статистику
    classified_count = (classified_df['assigned_category'] != '').sum()
    unclassified_count = len(classified_df) - classified_count
    
    print(f"\n📊 РЕЗУЛЬТАТЫ КЛАССИФИКАЦИИ:")
    print(f"   ✅ Классифицировано: {classified_count}")
    print(f"   ❌ Не классифицировано: {unclassified_count}")
    
    # Показываем распределение по категориям
    if classified_count > 0:
        print(f"\n📈 РАСПРЕДЕЛЕНИЕ ПО КАТЕГОРИЯМ:")
        category_counts = classified_df[classified_df['assigned_category'] != '']['assigned_category'].value_counts()
        for category, count in category_counts.items():
            print(f"   {category}: {count} задач")
    
    # Сохраняем результаты
    os.makedirs(data_folder, exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    results_file = os.path.join(data_folder, f"classified_tasks_{timestamp}.xlsx")
    classified_df.to_excel(results_file, index=False, sheet_name='Classified_Tasks')
    
    # Основной файл результатов
    main_results_file = os.path.join(data_folder, "classified_tasks.xlsx")
    classified_df.to_excel(main_results_file, index=False, sheet_name='Classified_Tasks')
    
    print(f"\n✅ Результаты сохранены:")
    print(f"   📄 {results_file}")
    print(f"   📄 {main_results_file}")
    
    return classified_df, main_results_file


def main_classification():
    """Основная функция для классификации задач"""
    
    try:
        # Загружаем данные
        tasks_df, categories_df = load_tasks_and_categories()
        
        # Классифицируем задачи
        classified_df, results_file = classify_all_tasks(tasks_df, categories_df)
        
        print("\n🎉 КЛАССИФИКАЦИЯ ЗАВЕРШЕНА!")
        return classified_df, results_file
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return None, None


if __name__ == "__main__":
    main_classification()
