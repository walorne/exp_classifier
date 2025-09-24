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


def process_batch_with_accumulation(batch_data, max_retries=3, prompt_name=None, accumulated_categories=None, accumulated_categories_lock=None, verbose_logging=False):
    """
    Обрабатывает батч задач с накоплением категорий в реальном времени
    
    Args:
        batch_data: tuple (batch_tasks, batch_num, total_batches)
        max_retries: максимальное количество попыток
        prompt_name: название промпта для использования (если None, используется активный)
        accumulated_categories: общий список накопленных категорий
        accumulated_categories_lock: блокировка для безопасного доступа к общему списку
        verbose_logging: включить детальное логирование в файл
    
    Returns:
        tuple: (batch_num, categories_list, success, error_msg)
    """
    import threading
    
    batch_tasks, batch_num, total_batches = batch_data
    
    # Создаем отдельный клиент для каждого потока
    llm_client = create_default_client()
    
    for attempt in range(max_retries):
        try:
            # Получаем текущие накопленные категории (с блокировкой)
            current_categories = []
            if accumulated_categories_lock:
                with accumulated_categories_lock:
                    current_categories = accumulated_categories.copy()
            
            # Минимальный вывод - только для отладки при необходимости
            # (все детальные выводы убраны)
            
            response = process_batch_for_categories(batch_tasks, batch_num, total_batches, llm_client, prompt_name, current_categories)
            categories = parse_categories_response(response)
            
            # Фильтруем дубликаты - оставляем только новые категории
            filtered_categories = filter_new_categories(categories, current_categories)
            
            # Добавляем только новые категории к общему списку (с блокировкой)
            if accumulated_categories_lock and filtered_categories:
                with accumulated_categories_lock:
                    accumulated_categories.extend(filtered_categories)
                    # Опциональное логирование в файл (не нарушает прогресс-бар)
                    if verbose_logging:
                        with open("category_generation_stats.log", "a", encoding="utf-8") as f:
                            f.write(f"Батч {batch_num}: добавлено {len(filtered_categories)} новых категорий (отфильтровано {len(categories) - len(filtered_categories)} дубликатов)\n")
                        # Используем tqdm.write() для вывода в консоль без нарушения прогресс-бара
                        tqdm.write(f"✅ Батч {batch_num}: добавлено {len(filtered_categories)} новых категорий (отфильтровано {len(categories) - len(filtered_categories)} дубликатов)")
            
            return batch_num, filtered_categories, True, None
            
        except Exception as e:
            error_msg = f"Попытка {attempt + 1}/{max_retries}: {str(e)}"
            if attempt == max_retries - 1:  # Последняя попытка
                return batch_num, [], False, error_msg
            
            # Небольшая задержка между попытками
            time.sleep(1.0 * (attempt + 1))
    
    return batch_num, [], False, "Превышено количество попыток"


def process_batch_for_categories_with_retries(batch_data, max_retries=3, prompt_name=None, existing_categories=None, temp_dir=None):
    """
    Обрабатывает батч задач с повторными попытками при ошибках
    
    Args:
        batch_data: tuple (batch_tasks, batch_num, total_batches)
        max_retries: максимальное количество попыток
        prompt_name: название промпта для использования (если None, используется активный)
        existing_categories: список уже существующих категорий для контекста
        temp_dir: временная папка для сохранения результатов
    
    Returns:
        tuple: (batch_num, categories_list, success, error_msg)
    """
    batch_tasks, batch_num, total_batches = batch_data
    
    # Создаем отдельный клиент для каждого потока
    llm_client = create_default_client()
    
    for attempt in range(max_retries):
        try:
            response = process_batch_for_categories(batch_tasks, batch_num, total_batches, llm_client, prompt_name, existing_categories)
            categories = parse_categories_response(response)
            
            # Сохраняем результат во временный файл
            if temp_dir and categories:
                temp_file = os.path.join(temp_dir, f"batch_{batch_num:03d}.xlsx")
                temp_df = pd.DataFrame(categories)
                temp_df.to_excel(temp_file, index=False)
            
            return batch_num, categories, True, None
            
        except Exception as e:
            error_msg = f"Попытка {attempt + 1}/{max_retries}: {str(e)}"
            if attempt == max_retries - 1:  # Последняя попытка
                return batch_num, [], False, error_msg
            
            # Небольшая задержка между попытками
            time.sleep(1.0 * (attempt + 1))
    
    return batch_num, [], False, "Превышено количество попыток"


def process_batch_for_categories(batch_tasks, batch_num, total_batches, llm_client, prompt_name=None, existing_categories=None):
    """Обрабатывает батч задач для создания категорий"""
    
    # Создаем менеджер промптов
    prompt_manager = create_category_prompt_manager()
    
    # Собираем тексты для классификации
    texts_for_classification = []
    for _, row in batch_tasks.iterrows():
        # Проверяем наличие всех колонок
        issuetype = row.get('issuetype', 'Неизвестно')
        title = row.get('title', 'Без названия')
        description = row.get('description', 'Без описания')
        summary_text = row.get('summary', '') if 'summary' in row else ''
        
        # Формируем текст в зависимости от доступных данных
        text_parts = [
            f"Тип: {issuetype}",
            f"Название: {title}",
            f"Описание: {description}"
        ]
        
        if summary_text:
            text_parts.append(f"Саммаризация: {summary_text}")
            
        text = "\n".join(text_parts)
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

    # Получаем отформатированный промпт из менеджера с существующими категориями
    prompt = prompt_manager.format_category_generation_prompt(
        tasks_text=tasks_text, 
        prompt_name=prompt_name,
        existing_categories=existing_categories
    )
    # with open("category_generation_prompt_log.txt", "a", encoding="utf-8") as f:
    #     f.write(f"\n--- БАТЧ {batch_num}/{total_batches} ---\n")
    #     f.write(prompt)
    #     f.write("\n")

    response = llm_client.simple_chat(prompt)

    # with open("category_generation_response_log.txt", "a", encoding="utf-8") as f:
    #     f.write(f"\n--- БАТЧ {batch_num}/{total_batches} ---\n")
    #     f.write(response)
    #     f.write("\n")

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


def filter_new_categories(new_categories, existing_categories):
    """
    Фильтрует новые категории, исключая дубликаты существующих
    
    Args:
        new_categories: список новых категорий от модели
        existing_categories: список существующих категорий
    
    Returns:
        список уникальных новых категорий
    """
    if not existing_categories:
        return new_categories
    
    # Создаем множество названий существующих категорий для быстрого поиска
    existing_names = {cat.get('Название', '').lower().strip() for cat in existing_categories}
    
    filtered_categories = []
    for new_cat in new_categories:
        new_name = new_cat.get('Название', '').lower().strip()
        
        # Проверяем, есть ли такая категория уже
        if new_name not in existing_names:
            filtered_categories.append(new_cat)
        # Отфильтрованные категории не логируем, чтобы не нарушать прогресс-бар
    
    return filtered_categories


def generate_categories_from_tasks(tasks_df, batch_size=50, data_folder="classification_data", save_timestamped=True, max_workers=2, max_retries=3, prompt_name=None, existing_categories=None, verbose_logging=False):
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
        existing_categories (list): список уже существующих категорий для контекста (только начальные)
        verbose_logging (bool): включить детальное логирование в файл
    
    Returns:
        pd.DataFrame: DataFrame с категориями
        str: путь к основному файлу категорий
    """
    # Разбиваем на батчи
    total_batches = (len(tasks_df) + batch_size - 1) // batch_size
    
    # Инициализируем накопитель категорий в памяти
    accumulated_categories = existing_categories.copy() if existing_categories else []
    
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
    
    print(f"🤖 Генерация категорий: {total_batches} батчей по {batch_size} задач")
    print(f"📋 Начальное количество категорий: {len(accumulated_categories)}")
    
    all_categories = []

    # Счетчики для статистики
    success_count = 0
    error_count = 0
    retry_count = 0

    # Гибридный подход: многопоточность + накопление в реальном времени
    print(f"🚀 Используем гибридный подход: {max_workers} потоков + накопление в реальном времени")
    
    # Создаем общий список для накопления категорий (с блокировкой)
    import threading
    accumulated_categories_lock = threading.Lock()
    
    # Подготавливаем данные для обработки
    batch_data = []
    for i in range(0, len(tasks_df), batch_size):
        batch_num = (i // batch_size) + 1
        batch_tasks = tasks_df.iloc[i:i+batch_size]
        batch_data.append((batch_tasks, batch_num, total_batches))
        
        # Ограничиваем количество батчей для отладки (отключено)
        # if len(batch_data) >= 3:  # Ограничиваем 3 батчами для отладки
        #     print(f"🔧 ОТЛАДКА: Ограничиваем обработку 3 батчами")
        #     break
    
    # Многопоточная обработка с накоплением в реальном времени
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Отправляем все батчи в пул потоков
        future_to_batch = {
            executor.submit(process_batch_with_accumulation, data, max_retries, prompt_name, accumulated_categories, accumulated_categories_lock, verbose_logging): data[1] 
            for data in batch_data
        }
        
        # Обрабатываем результаты по мере готовности
        with tqdm(total=total_batches, 
                  desc="🤖 Обработка батчей", 
                  unit="батч",
                  ncols=80,
                  leave=True,
                  dynamic_ncols=False,
                  miniters=1,  # Обновляем каждую итерацию
                  mininterval=0.5,  # Минимум 0.5 секунды между обновлениями
                  maxinterval=5.0,  # Максимум 5 секунд между обновлениями
                  smoothing=0.1,
                  position=0,
                  ascii=True,
                  bar_format='{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]') as pbar:
            
            processed_batches = 0
            for future in as_completed(future_to_batch):
                batch_num, categories, success, error_msg = future.result()
                
                if success:
                    # categories уже отфильтрованы в process_batch_with_accumulation
                    all_categories.extend(categories)
                    success_count += 1
                else:
                    error_count += 1
                    if "Попытка" in str(error_msg):
                        retry_count += 1
                
                processed_batches += 1
                
                # Обновляем описание прогресс-бара только каждые 5 батчей или в конце
                if processed_batches % 5 == 0 or processed_batches == total_batches:
                    with accumulated_categories_lock:
                        current_count = len(accumulated_categories)
                    pbar.set_description(f"🤖 Обработано: {processed_batches}/{total_batches} | Накоплено: {current_count} категорий")
                    pbar.refresh()  # Принудительно обновляем отображение
                    
                    # Выводим статистику через tqdm.write() чтобы не нарушать прогресс-бар
                    tqdm.write(f"📊 Статистика: обработано {processed_batches}/{total_batches} батчей, накоплено {current_count} категорий")
                
                # Обновляем прогресс-бар
                pbar.update(1)
            
            # Финальное обновление описания
            with accumulated_categories_lock:
                final_count = len(accumulated_categories)
            pbar.set_description(f"🤖 Завершено: {total_batches}/{total_batches} | Итого: {final_count} категорий")
            pbar.refresh()  # Принудительно обновляем финальное состояние
            
            # Финальная статистика через tqdm.write()
            tqdm.write(f"🎉 Завершено: {total_batches}/{total_batches} батчей, итого {final_count} категорий")
    
    # Накопление завершено
    
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


def main():
    """
    Основная функция для тестирования генерации категорий с существующими категориями
    """
    print("🧪 Тестирование генерации категорий с существующими категориями")
    print("=" * 60)
    
    # Конфигурация для тестирования
    DATA_FOLDER = "classification_data/AMT"
    BATCH_SIZE = 5
    MAX_WORKERS = 10  # Возвращаем нормальное количество потоков
    MAX_RETRIES = 3
    PROMPT_NAME = None  # None = активный промпт
    # MAX_BATCHES_FOR_DEBUG = 3  # Ограничиваем количество батчей для отладки (отключено)
    
    # Загружаем задачи из файла
    tasks_file = os.path.join(DATA_FOLDER, "tasks_summary.xlsx")
    if not os.path.exists(tasks_file):
        print(f"❌ Файл с задачами не найден: {tasks_file}")
        print("💡 Поместите файл tasks.xlsx в папку и запустите скрипт снова")
        return
    
    try:
        tasks_df = pd.read_excel(tasks_file)
        print(f"✅ Загружено {len(tasks_df)} задач из файла: {tasks_file}")
        
        # Структура данных загружена
        
    except Exception as e:
        print(f"❌ Ошибка загрузки файла задач: {e}")
        return
    
    # Загружаем только начальные категории (если есть отдельный файл)
    initial_categories = []
    initial_categories_file = os.path.join(DATA_FOLDER, "initial_categories.xlsx")
    
    if os.path.exists(initial_categories_file):
        try:
            initial_categories_df = pd.read_excel(initial_categories_file)
            initial_categories = initial_categories_df.to_dict('records')
            print(f"📋 Загружено {len(initial_categories)} начальных категорий")
        except Exception as e:
            print(f"⚠️ Ошибка загрузки начальных категорий: {e}")
            initial_categories = []
    else:
        print("📋 Начальных категорий не найдено (будет создан новый набор)")
    
    # Начальные категории загружены
    
    # Настройки загружены
    
    # Выполняем генерацию
    try:
        categories_df, categories_file = generate_categories_from_tasks(
            tasks_df=tasks_df,
            batch_size=BATCH_SIZE,
            data_folder=DATA_FOLDER,
            save_timestamped=False,
            max_workers=MAX_WORKERS,
            max_retries=MAX_RETRIES,
            prompt_name=PROMPT_NAME,
            existing_categories=initial_categories
        )
        
        print(f"\n🎉 ГЕНЕРАЦИЯ ЗАВЕРШЕНА!")
        print(f"   Создано категорий: {len(categories_df)}")
        print(f"   Файл сохранен: {categories_file}")
        
    except Exception as e:
        print(f"\n❌ ОШИБКА ПРИ ГЕНЕРАЦИИ: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
