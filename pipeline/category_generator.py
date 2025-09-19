"""
Модуль для генерации категорий из задач с помощью LLM
Версия 0.3 - с поддержкой настраиваемых промптов
"""
import pandas as pd
import os
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from clients.ai_client import create_default_client
from utils.file_utils import safe_save_excel
from prompts.prompt_manager import create_category_prompt_manager


def process_batch_for_categories_with_retries(batch_data, max_retries=3, prompt_name=None):
    """
    Обрабатывает батч задач с повторными попытками при ошибках
    
    Args:
        batch_data: tuple (batch_tasks, batch_num, total_batches)
        max_retries: максимальное количество попыток
        prompt_name: название промпта для использования (если None, используется активный)
    
    Returns:
        tuple: (batch_num, categories_list, success, error_msg)
    """
    batch_tasks, batch_num, total_batches = batch_data
    
    # Создаем отдельный клиент для каждого потока
    llm_client = create_default_client()
    
    for attempt in range(max_retries):
        try:
            response = process_batch_for_categories(batch_tasks, batch_num, total_batches, llm_client, prompt_name)
            categories = parse_categories_response(response)
            return batch_num, categories, True, None
            
        except Exception as e:
            error_msg = f"Попытка {attempt + 1}/{max_retries}: {str(e)}"
            if attempt == max_retries - 1:  # Последняя попытка
                return batch_num, [], False, error_msg
            
            # Небольшая задержка между попытками
            time.sleep(1.0 * (attempt + 1))
    
    return batch_num, [], False, "Превышено количество попыток"


def process_batch_for_categories(batch_tasks, batch_num, total_batches, llm_client, prompt_name=None):
    """Обрабатывает батч задач для создания категорий"""
    
    # Создаем менеджер промптов
    prompt_manager = create_category_prompt_manager()
    
    # Собираем тексты для классификации
    texts_for_classification = []
    for _, row in batch_tasks.iterrows():
        text = f"Тип: {row['issuetype']}\nНазвание: {row['title']}\nОписание: {row['description']}\nСаммаризация: {row['summary']}"
        texts_for_classification.append(text)

    # Формируем текст задач для промпта
    tasks_text = f"ЗАДАЧИ ДЛЯ АНАЛИЗА (батч {batch_num}/{total_batches}):\n"
    tasks_text += chr(10).join([f"{i+1}. {text}" for i, text in enumerate(texts_for_classification)])
    
    # Добавляем форматирование для CSV (пока оставляем как есть для совместимости)
    tasks_text += "\n\nВЕРНИ РЕЗУЛЬТАТ СТРОГО В ФОРМАТЕ CSV (разделитель - точка с запятой):\n"
    tasks_text += "Название;Описание;Ключевые_слова;Типы_задач\n\n"
    tasks_text += "ВАЖНО:\n"
    tasks_text += "- НЕ добавляй заголовки столбцов\n"
    tasks_text += "- НЕ добавляй номера строк\n"
    tasks_text += "- Каждая категория на новой строке\n"
    tasks_text += "- Используй точку с запятой как разделитель\n\n"
    tasks_text += "# Пример:\n"
    tasks_text += "# API интеграции;Настройка и разработка API интеграций;api,интеграция,настройка,разработка;Task,Story\n"
    tasks_text += "# Работа с ошибками;Исправление ошибок и багов в системе;ошибка,баг,исправление,отладка;Bug,Task"

    # Получаем отформатированный промпт из менеджера
    prompt = prompt_manager.format_category_generation_prompt(
        tasks_text=tasks_text, 
        prompt_name=prompt_name
    )

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


def generate_categories_from_tasks(tasks_df, batch_size=50, data_folder="classification_data", save_timestamped=True, max_workers=2, max_retries=3, prompt_name=None):
    """
    Генерирует категории из задач батчами с многопоточностью
    
    Args:
        tasks_df (pd.DataFrame): DataFrame с задачами
        batch_size (int): размер батча
        data_folder (str): папка для сохранения файлов
        save_timestamped (bool): сохранять ли файлы с временными метками
        max_workers (int): количество потоков для обработки
        max_retries (int): количество повторных попыток при ошибке
        prompt_name (str): название промпта для использования (если None, используется активный)
    
    Returns:
        pd.DataFrame: DataFrame с категориями
        str: путь к основному файлу категорий
    """
    # Разбиваем на батчи
    total_batches = (len(tasks_df) + batch_size - 1) // batch_size
    
    # Показываем информацию о промпте
    prompt_manager = create_category_prompt_manager()
    if prompt_name:
        prompts_info = prompt_manager.list_category_generation_prompts()
        active_prompt_info = prompts_info.get(prompt_name, {"name": prompt_name})
        print(f"\n🎯 Используемый промпт: {active_prompt_info['name']} ({prompt_name})")
    else:
        config = prompt_manager.load_category_generation_config()
        active_prompt = config.get('active_prompt', 'basic_v1')
        prompts_info = prompt_manager.list_category_generation_prompts()
        active_prompt_info = prompts_info.get(active_prompt, {"name": active_prompt})
        print(f"\n🎯 Активный промпт: {active_prompt_info['name']} ({active_prompt})")
    
    print(f"🤖 Генерация категорий: {total_batches} батчей по {batch_size} задач (потоков: {max_workers})")
    
    all_categories = []

    # Подготавливаем данные для обработки
    batch_data = []
    for i in range(0, len(tasks_df), batch_size):
        batch_num = (i // batch_size) + 1
        batch_tasks = tasks_df.iloc[i:i+batch_size]
        batch_data.append((batch_tasks, batch_num, total_batches))
    
    # Счетчики для статистики
    success_count = 0
    error_count = 0
    retry_count = 0

    # Многопоточная обработка с прогресс-баром
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Отправляем все батчи в пул потоков
        future_to_batch = {
            executor.submit(process_batch_for_categories_with_retries, data, max_retries, prompt_name): data[1] 
            for data in batch_data
        }
        
        # Обрабатываем результаты по мере готовности
        with tqdm(total=total_batches, 
                  desc="🤖 Обработка батчей", 
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
                batch_num, categories, success, error_msg = future.result()
                
                if success:
                    all_categories.extend(categories)
                    success_count += 1
                else:
                    error_count += 1
                    if "Попытка" in str(error_msg):
                        retry_count += 1
                
                # Обновляем прогресс-бар только с базовой информацией
                pbar.update(1)
    
    # Создаем DataFrame с категориями (после закрытия прогресс-бара)
    categories_df = pd.DataFrame(all_categories)

    # Убираем дубликаты по названию (оставляем первое вхождение)
    categories_df = categories_df.drop_duplicates(subset=['Название'], keep='first')

    # Краткая статистика
    print(f"\n✅ Обработано {success_count}/{total_batches} батчей, создано {len(categories_df)} категорий")
    
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
