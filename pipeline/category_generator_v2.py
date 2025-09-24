"""
Модуль для генерации категорий из задач с помощью LLM
Версия 2.0 - переписанная для обработки по одной задаче с использованием справочника категорий
"""
import pandas as pd
import os
import time
import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from clients.ai_client import create_default_client
from utils.file_utils import safe_save_excel
from prompts.prompt_manager import create_category_prompt_manager


def process_single_task_with_retries(task_data, max_retries=3, prompt_name=None, accumulated_categories=None, accumulated_categories_lock=None):
    """
    Обрабатывает одну задачу с повторными попытками при ошибках

    Args:
        task_data: tuple (task_index, task_row) - индекс и данные задачи
        max_retries: максимальное количество попыток
        prompt_name: название промпта для использования (если None, используется активный)
        accumulated_categories: общий список накопленных категорий
        accumulated_categories_lock: блокировка для безопасного доступа к общему списку

    Returns:
        tuple: (task_index, categories_list, success, error_msg)
    """
    task_index, task_row = task_data

    # Создаем отдельный клиент для каждого потока
    llm_client = create_default_client()

    for attempt in range(max_retries):
        try:
            # Получаем текущие накопленные категории (с блокировкой)
            current_categories = []
            if accumulated_categories_lock:
                with accumulated_categories_lock:
                    current_categories = accumulated_categories.copy()

            response = process_single_task_for_categories(task_row, llm_client, prompt_name, current_categories)
            categories = parse_categories_response(response)

            # Фильтруем дубликаты - оставляем только новые категории
            filtered_categories = filter_new_categories(categories, current_categories)

            # Добавляем только новые категории к общему списку (с блокировкой)
            if accumulated_categories_lock and filtered_categories:
                with accumulated_categories_lock:
                    accumulated_categories.extend(filtered_categories)

            return task_index, filtered_categories, True, None

        except Exception as e:
            error_msg = f"Попытка {attempt + 1}/{max_retries}: {str(e)}"
            if attempt == max_retries - 1:  # Последняя попытка
                return task_index, [], False, error_msg

            # Небольшая задержка между попытками
            time.sleep(0.5 * (attempt + 1))

    return task_index, [], False, "Превышено количество попыток"


def process_single_task_for_categories(task_row, llm_client, prompt_name=None, existing_categories=None):
    """Обрабатывает одну задачу для создания категорий"""

    # Создаем менеджер промптов
    prompt_manager = create_category_prompt_manager()

    # Формируем текст задачи
    issuetype = task_row.get('issuetype', 'Неизвестно')
    title = task_row.get('title', 'Без названия')
    description = task_row.get('description', 'Без описания')
    comments = task_row.get('comments', 'Без комментариев')
    summary_text = task_row.get('summary', '') if 'summary' in task_row else ''

    # Формируем текст в зависимости от доступных данных
    text_parts = [
        f"Тип: {issuetype}",
        f"Название: {title}",
        f"Описание: {description}"
    ]

    if summary_text:
        text_parts.append(f"Саммаризация: {summary_text}")
    
    if comments:
        text_parts.append(f"Комментарии: {comments}")

    task_text = "\n".join(text_parts)

    # Получаем отформатированный промпт из менеджера с существующими категориями и справочником систем
    prompt = prompt_manager.format_category_generation_prompt(
        tasks_text=task_text,
        prompt_name=prompt_name,
        existing_categories=existing_categories
    )

    fileprint=False
    if fileprint:
        with open("category_generation_prompt_log.txt", "a", encoding="utf-8") as f:
            f.write(f"\n--- БАТЧ ---\n")
            f.write(prompt)
            f.write("\n")

    response = llm_client.simple_chat(prompt)

    if fileprint:
        with open("category_generation_response_log.txt", "a", encoding="utf-8") as f:
            f.write(f"\n--- БАТЧ ---\n")
            f.write(response)
            f.write("\n")

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

    return filtered_categories



def generate_categories_from_tasks(tasks_df, data_folder="classification_data", save_timestamped=True, max_workers=100, max_retries=3, prompt_name=None, existing_categories=None, verbose_logging=False):
    """
    Генерирует категории из задач по одной с многопоточностью и использованием справочника систем

    Args:
        tasks_df (pd.DataFrame): DataFrame с задачами
        data_folder (str): папка для сохранения файлов
        save_timestamped (bool): сохранять ли файлы с временными метками
        max_workers (int): количество потоков для обработки (по умолчанию 100)
        max_retries (int): количество повторных попыток при ошибке
        prompt_name (str): название промпта для использования (если None, используется активный)
        existing_categories (list): список уже существующих категорий для контекста (только начальные)
        verbose_logging (bool): включить детальное логирование в файл

    Returns:
        pd.DataFrame: DataFrame с категориями
        str: путь к основному файлу категорий
    """
    total_tasks = len(tasks_df)

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

    print(f"🤖 Генерация категорий: {total_tasks} задач по одной с {max_workers} потоками")
    print(f"📋 Начальное количество категорий: {len(accumulated_categories)}")

    all_categories = []

    # Счетчики для статистики
    success_count = 0
    error_count = 0
    retry_count = 0

    # Создаем общий список для накопления категорий (с блокировкой)
    accumulated_categories_lock = threading.Lock()

    # Подготавливаем данные для обработки (по одной задаче)
    task_data = []
    for task_index, (_, task_row) in enumerate(tasks_df.iterrows()):
        task_data.append((task_index, task_row))

    # Многопоточная обработка по одной задаче
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Отправляем все задачи в пул потоков
        future_to_task = {
            executor.submit(process_single_task_with_retries, task, max_retries, prompt_name, accumulated_categories, accumulated_categories_lock): task[0]
            for task in task_data
        }

        # Обрабатываем результаты по мере готовности
        with tqdm(total=total_tasks,
                  desc="🤖 Обработка задач",
                  unit="задача",
                  ncols=80,
                  leave=True,
                  dynamic_ncols=False,
                  miniters=1,
                  mininterval=0.5,
                  maxinterval=5.0,
                  smoothing=0.1,
                  position=0,
                  ascii=True,
                  bar_format='{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]') as pbar:

            processed_tasks = 0
            for future in as_completed(future_to_task):
                task_index, categories, success, error_msg = future.result()

                if success:
                    # categories уже отфильтрованы в process_single_task_with_retries
                    all_categories.extend(categories)
                    success_count += 1
                else:
                    error_count += 1
                    if "Попытка" in str(error_msg):
                        retry_count += 1

                processed_tasks += 1

                # Обновляем описание прогресс-бара только каждые 10 задач или в конце
                if processed_tasks % 10 == 0 or processed_tasks == total_tasks:
                    with accumulated_categories_lock:
                        current_count = len(accumulated_categories)
                    pbar.set_description(f"🤖 Обработано: {processed_tasks}/{total_tasks} | Накоплено: {current_count} категорий")
                    pbar.refresh()

                    # Выводим статистику через tqdm.write() чтобы не нарушать прогресс-бар
                    tqdm.write(f"📊 Статистика: обработано {processed_tasks}/{total_tasks} задач, накоплено {current_count} категорий")

                # Обновляем прогресс-бар
                pbar.update(1)

            # Финальное обновление описания
            with accumulated_categories_lock:
                final_count = len(accumulated_categories)
            pbar.set_description(f"🤖 Завершено: {total_tasks}/{total_tasks} | Итого: {final_count} категорий")
            pbar.refresh()

            # Финальная статистика через tqdm.write()
            tqdm.write(f"🎉 Завершено: {total_tasks}/{total_tasks} задач, итого {final_count} категорий")

    # Накопление завершено

    # Создаем DataFrame с категориями (после закрытия прогресс-бара)
    categories_df = pd.DataFrame(all_categories)

    # Убираем дубликаты по названию (оставляем первое вхождение)
    categories_df = categories_df.drop_duplicates(subset=['Название'], keep='first')

    # Краткая статистика
    print(f"\n✅ Обработано {success_count}/{total_tasks} задач, создано {len(categories_df)} категорий")

    if error_count > 0:
        print(f"⚠️ Ошибок обработки: {error_count}")

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
    Основная функция для тестирования новой генерации категорий по одной задаче
    """
    print("🧪 Тестирование новой генерации категорий (по одной задаче)")
    print("=" * 60)

    # Конфигурация для тестирования
    DATA_FOLDER = "classification_data/MPSM"
    MAX_WORKERS = 100  # Возвращаем нормальное количество потоков
    MAX_RETRIES = 3
    PROMPT_NAME = None  # None = активный промпт

    # Загружаем задачи из файла
    tasks_file = os.path.join(DATA_FOLDER, "tasks_summary.xlsx")
    if not os.path.exists(tasks_file):
        print(f"❌ Файл с задачами не найден: {tasks_file}")
        print("💡 Поместите файл tasks.xlsx в папку и запустите скрипт снова")
        return

    try:
        tasks_df = pd.read_excel(tasks_file)
        print(f"✅ Загружено {len(tasks_df)} задач из файла: {tasks_file}")

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

    # Выполняем генерацию
    try:
        categories_df, categories_file = generate_categories_from_tasks(
            tasks_df=tasks_df,
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
