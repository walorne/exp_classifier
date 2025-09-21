"""
Модуль для присвоения финальных категорий JIRA задачам
"""
import pandas as pd
import os
import re
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from clients.ai_client import create_default_client
from utils.file_utils import safe_save_excel


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


def classify_single_task_with_retries(task_data, categories_df, max_retries=3):
    """
    Классифицирует одну задачу с повторными попытками при ошибках
    
    Args:
        task_data: tuple (index, task_row) - индекс и данные задачи
        categories_df: DataFrame с категориями
        max_retries: максимальное количество попыток
    
    Returns:
        tuple: (index, category, success, error_msg)
    """
    index, task_row = task_data
    task_key = task_row.get('key', f'Task_{index}')
    
    for attempt in range(max_retries):
        try:
            # Создаем отдельный клиент для каждой попытки
            llm_client = create_default_client()
            
            category = classify_single_task_with_llm(task_row, categories_df, llm_client)
            return index, category, True, None
            
        except Exception as e:
            error_msg = f"Попытка {attempt + 1}/{max_retries}: {str(e)}"
            
            if attempt == max_retries - 1:  # Последняя попытка
                return index, "Ошибка классификации", False, error_msg
            
            # Небольшая задержка между попытками
            time.sleep(0.5 * (attempt + 1))
    
    return index, "Ошибка классификации", False, "Превышено количество попыток"


def classify_single_task_with_llm(task_row, categories_df, llm_client):
    """Классифицирует одну задачу с помощью LLM"""
    
    # Подготавливаем текст задачи
    task_text = f"Тип: {task_row.get('issuetype', 'Не указан')}\n"
    task_text += f"Название: {task_row.get('title', 'Не указано')}\n"
    task_text += f"Описание: {task_row.get('description', 'Не указано')}\n"
    
    # Добавляем саммаризацию если есть
    if 'summary' in task_row and pd.notna(task_row['summary']):
        task_text += f"Саммаризация: {task_row['summary']}\n"
    
    # Формируем список категорий
    categories_text = ""
    for _, cat_row in categories_df.iterrows():
        categories_text += f"- {cat_row['Название']}: {cat_row['Описание']}\n"
    
    # Создаем промпт для классификации
    prompt = f"""Ты эксперт по классификации рабочих задач. Проанализируй задачу и определи, к какой категории она относится.

ЗАДАЧА ДЛЯ КЛАССИФИКАЦИИ:
{task_text}

ДОСТУПНЫЕ КАТЕГОРИИ:
{categories_text}

ТРЕБОВАНИЯ:
1. Выбери ТОЛЬКО ОДНУ наиболее подходящую категорию из списка выше
2. Анализируй содержание задачи, а не только название
3. Учитывай тип задачи и контекст выполняемых работ
4. ПРИОРИТЕТ анализа: используй в первую очередь поле "Саммаризация" - это подготовленные для классификации данные
5. Дополнительно анализируй название, описание и тип задачи для более точного определения

ФОРМАТ ОТВЕТА:
Верни ТОЛЬКО название категории без дополнительных объяснений.

ПРИМЕР:
Разработка новых функций

ВЕРНИ ТОЛЬКО НАЗВАНИЕ КАТЕГОРИИ:"""

    try:
        response = llm_client.simple_chat(prompt)
        category_name = response.strip()
        
        # Проверяем, что категория существует в списке
        if category_name in categories_df['Название'].values:
            return category_name
        else:
            # Пытаемся найти похожую категорию
            for _, cat_row in categories_df.iterrows():
                if category_name.lower() in cat_row['Название'].lower() or cat_row['Название'].lower() in category_name.lower():
                    return cat_row['Название']
            
            # Если не нашли, возвращаем первую категорию как fallback
            fallback_category = categories_df.iloc[0]['Название']
            return fallback_category
            
    except Exception as e:
        raise Exception(f"Ошибка классификации задачи: {str(e)}")


def classify_batch_with_retries(batch_data, categories_df, max_retries=3):
    """
    Классифицирует батч задач с повторными попытками при ошибках
    
    Args:
        batch_data: tuple (tasks_batch, batch_num, total_batches)
        categories_df: DataFrame с категориями
        max_retries: максимальное количество попыток
    
    Returns:
        tuple: (batch_num, classifications_dict, success, error_msg)
    """
    tasks_batch, batch_num, total_batches = batch_data
    
    # Создаем отдельный клиент для каждого потока
    llm_client = create_default_client()
    
    for attempt in range(max_retries):
        try:
            classifications = classify_tasks_with_llm(tasks_batch, categories_df, batch_num, total_batches, llm_client)
            return batch_num, classifications, True, None
            
        except Exception as e:
            error_msg = f"Попытка {attempt + 1}/{max_retries}: {str(e)}"
            if attempt == max_retries - 1:  # Последняя попытка
                return batch_num, {}, False, error_msg
            
            # Небольшая задержка между попытками
            time.sleep(1.0 * (attempt + 1))
    
    return batch_num, {}, False, "Превышено количество попыток"


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
        if row.get('summary'):
            tasks_text += f"   Саммаризация: {row['summary']}\n"
        if row['description']:
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
4. ПРИОРИТЕТ анализа: используй в первую очередь поле "Саммаризация" - это подготовленные для классификации данные
5. Дополнительно анализируй название, описание и тип задачи для более точного определения

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


def classify_all_tasks(tasks_df, categories_df, batch_size=20, data_folder="classification_data", save_timestamped=True, max_workers=5, classification_mode="single", max_retries=3):
    """
    Классифицирует все задачи по финальным категориям с многопоточностью
    
    Args:
        tasks_df (pd.DataFrame): DataFrame с задачами
        categories_df (pd.DataFrame): DataFrame с финальными категориями (может быть None)
        batch_size (int): размер батча для LLM (используется только в batch режиме)
        data_folder (str): папка для сохранения файлов
        save_timestamped (bool): сохранять ли файлы с временными метками
        max_workers (int): количество потоков для обработки
        classification_mode (str): режим классификации ("single" или "batch")
        max_retries (int): количество повторных попыток при ошибке
    
    Returns:
        pd.DataFrame: DataFrame с классифицированными задачами
        str: путь к файлу с результатами
    """
    # Если categories_df не передан, пытаемся загрузить из файла
    if categories_df is None:
        final_categories_file = os.path.join(data_folder, "final_categories.xlsx")
        if os.path.exists(final_categories_file):
            try:
                categories_df = pd.read_excel(final_categories_file)
                print(f"📋 Загружены финальные категории из файла: {len(categories_df)} категорий")
                
                # Детальная информация о загруженных категориях
                print(f"📊 Структура данных:")
                print(f"   - Колонки: {list(categories_df.columns)}")
                print(f"   - Размер: {categories_df.shape}")
                
                # Показываем первые несколько категорий
                print(f"📝 Первые 5 категорий:")
                for i, (_, row) in enumerate(categories_df.head().iterrows()):
                    print(f"   {i+1}. {row.get('Название', 'N/A')}")
                    if 'Описание' in row and pd.notna(row['Описание']):
                        desc = str(row['Описание'])[:100] + "..." if len(str(row['Описание'])) > 100 else str(row['Описание'])
                        print(f"      Описание: {desc}")
                
                # Проверяем наличие обязательных полей
                required_fields = ['Название', 'Описание']
                missing_fields = [field for field in required_fields if field not in categories_df.columns]
                if missing_fields:
                    print(f"⚠️ Отсутствуют обязательные поля: {missing_fields}")
                else:
                    print(f"✅ Все обязательные поля присутствуют")
                
                # Показываем все доступные поля
                print(f"📋 Доступные поля в файле:")
                for col in categories_df.columns:
                    non_null_count = categories_df[col].notna().sum()
                    print(f"   - {col}: {non_null_count}/{len(categories_df)} заполнено")
                
                # Проверяем на пустые значения в ключевых полях
                if 'Название' in categories_df.columns:
                    empty_names = categories_df['Название'].isna().sum()
                    if empty_names > 0:
                        print(f"⚠️ Найдено {empty_names} категорий без названия")
                
                if 'Описание' in categories_df.columns:
                    empty_descriptions = categories_df['Описание'].isna().sum()
                    if empty_descriptions > 0:
                        print(f"⚠️ Найдено {empty_descriptions} категорий без описания")
                    
            except Exception as e:
                print(f"❌ Ошибка загрузки финальных категорий: {e}")
                return None, None
        else:
            print("❌ Файл с финальными категориями не найден и categories_df не передан")
            return None, None
    # Выбираем режим классификации
    if classification_mode == "single":
        print(f"\n🎯 Классификация {len(tasks_df)} задач по одной (потоков: {max_workers})")
        return classify_tasks_single_mode(tasks_df, categories_df, data_folder, save_timestamped, max_workers, max_retries)
    else:
        print(f"\n🎯 Классификация {len(tasks_df)} задач батчами (потоков: {max_workers})")
        return classify_tasks_batch_mode(tasks_df, categories_df, batch_size, data_folder, save_timestamped, max_workers, max_retries)


def classify_tasks_single_mode(tasks_df, categories_df, data_folder, save_timestamped, max_workers, max_retries):
    """Классифицирует задачи по одной с многопоточностью"""
    
    # Копируем исходный DataFrame
    classified_df = tasks_df.copy()
    classified_df['assigned_category'] = ''
    classified_df['category_id'] = 0
    classified_df['classification_confidence'] = 'llm'
    
    # Счетчики для статистики
    success_count = 0
    error_count = 0
    retry_count = 0
    
    # Подготавливаем данные для обработки (index, row)
    task_data = [(index, row) for index, row in tasks_df.iterrows()]
    
    # Многопоточная обработка с прогресс-баром
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Отправляем все задачи в пул потоков
        future_to_task = {
            executor.submit(classify_single_task_with_retries, data, categories_df, max_retries): data[0] 
            for data in task_data
        }
        
        # Обрабатываем результаты по мере готовности
        with tqdm(total=len(tasks_df), 
                  desc="🎯 Классификация задач", 
                  unit="задача",
                  ncols=80,
                  leave=True,
                  dynamic_ncols=False,
                  miniters=0,
                  mininterval=0.5,
                  maxinterval=2.0,
                  smoothing=0.3,
                  position=0,
                  ascii=True,
                  bar_format='{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]') as pbar:
            
            for future in as_completed(future_to_task):
                index, category, success, error_msg = future.result()
                
                # Сохраняем результат
                classified_df.loc[index, 'assigned_category'] = category
                
                # Находим ID категории
                category_row = categories_df[categories_df['Название'] == category]
                if not category_row.empty:
                    classified_df.loc[index, 'category_id'] = category_row.index[0] + 1
                
                if success:
                    success_count += 1
                else:
                    error_count += 1
                    if "Попытка" in str(error_msg):
                        retry_count += 1
                
                pbar.update(1)
    
    # Краткая статистика (после закрытия прогресс-бара)
    print(f"\n✅ Обработано {success_count}/{len(tasks_df)} задач")
    
    return save_classification_results(classified_df, data_folder, save_timestamped)


def classify_tasks_batch_mode(tasks_df, categories_df, batch_size, data_folder, save_timestamped, max_workers, max_retries):
    """Классифицирует задачи батчами с многопоточностью"""
    
    # Копируем исходный DataFrame
    classified_df = tasks_df.copy()
    classified_df['assigned_category'] = ''
    classified_df['category_id'] = 0
    classified_df['classification_confidence'] = 'llm'
    
    # Разбиваем на батчи
    total_batches = (len(tasks_df) + batch_size - 1) // batch_size
    print(f"🎯 Классификация: {total_batches} батчей по {batch_size} задач (потоков: {max_workers})")
    
    # Подготавливаем данные для обработки
    batch_data = []
    for i in range(0, len(tasks_df), batch_size):
        batch_num = (i // batch_size) + 1
        tasks_batch = tasks_df.iloc[i:i+batch_size]
        batch_data.append((tasks_batch, batch_num, total_batches))
    
    # Счетчики для статистики
    success_count = 0
    error_count = 0
    retry_count = 0
    
    # Многопоточная обработка с прогресс-баром
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Отправляем все батчи в пул потоков
        future_to_batch = {
            executor.submit(classify_batch_with_retries, data, categories_df, max_retries): data[1] 
            for data in batch_data
        }
        
        # Обрабатываем результаты по мере готовности
        with tqdm(total=total_batches, 
                  desc="🎯 Обработка батчей", 
                  unit="батч",
                  ncols=80,
                  leave=True,
                  dynamic_ncols=False,
                  miniters=0,
                  mininterval=0.5,
                  maxinterval=2.0,
                  smoothing=0.3,
                  position=0,
                  ascii=True,
                  bar_format='{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]') as pbar:
            
            for future in as_completed(future_to_batch):
                batch_num, classifications, success, error_msg = future.result()
                
                if success:
                    # Применяем результаты классификации
                    apply_batch_classifications(classified_df, classifications, categories_df)
                    success_count += 1
                else:
                    error_count += 1
                    if "Попытка" in str(error_msg):
                        retry_count += 1
                
                pbar.update(1)
    
    # Краткая статистика (после закрытия прогресс-бара)
    print(f"\n✅ Обработано {success_count}/{total_batches} батчей")
    
    return save_classification_results(classified_df, data_folder, save_timestamped)


def apply_batch_classifications(classified_df, classifications, categories_df):
    """Применяет результаты классификации батча к DataFrame"""
    for task_key, category_name in classifications.items():
        # Найти задачу по ключу
        task_rows = classified_df[classified_df['key'] == task_key]
        if not task_rows.empty:
            task_index = task_rows.index[0]
            classified_df.loc[task_index, 'assigned_category'] = category_name
            
            # Найти ID категории
            category_row = categories_df[categories_df['Название'] == category_name]
            if not category_row.empty:
                classified_df.loc[task_index, 'category_id'] = category_row.index[0] + 1


def save_classification_results(classified_df, data_folder, save_timestamped):
    """Сохраняет результаты классификации в файлы"""
    
    # Подсчитываем статистику
    classified_count = (classified_df['assigned_category'] != '').sum()
    
    # Показываем распределение по категориям
    if classified_count > 0:
        category_counts = classified_df[classified_df['assigned_category'] != '']['assigned_category'].value_counts()
        print(f"📊 Топ-3 категории: {', '.join([f'{cat} ({count})' for cat, count in category_counts.head(3).items()])}")
    
    # Сохраняем результаты
    success1 = True
    results_file = None
    
    if save_timestamped:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        results_file = os.path.join(data_folder, f"classified_tasks_{timestamp}.xlsx")
        success1 = safe_save_excel(classified_df, results_file, 'Classified_Tasks', show_success_message=False)
    
    # Основной файл результатов
    main_results_file = os.path.join(data_folder, "classified_tasks.xlsx")
    success2 = safe_save_excel(classified_df, main_results_file, 'Classified_Tasks', show_success_message=False)
    
    if save_timestamped and success1 and success2:
        return classified_df, results_file
    elif success2:
        return classified_df, main_results_file
    else:
        return classified_df, None


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
