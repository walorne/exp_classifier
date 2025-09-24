"""
Основной скрипт для классификации JIRA задач
"""
import re
import os
import pandas as pd
from pipeline.jira_tasks_fetcher import fetch_and_save_tasks
from pipeline.task_summarizer import summarize_tasks
from pipeline.category_generator import generate_categories_from_tasks
from pipeline.category_consolidator import create_final_categories
from pipeline.task_classifier import classify_all_tasks, load_tasks_and_categories

# ===== КОНФИГУРАЦИЯ СКРИПТА =====
JQL = "project = MPSM AND issueFunction in issuesInEpics(\"ERP_JOBs ~ '00-00377754#000000002'\") AND created >= 2024-09-01 ORDER BY created DESC"
# JQL = "(project =  \"МП Funday\" OR project =  \"МП Остин\" )  AND issueFunction in issuesInEpics(\"ERP_JOBs ~'00-00377754#000000001'\") AND created >= 2024-09-01 AND created <= 2025-08-31 ORDER BY created DESC"
# JQL = "project = KISRMAC AND \"Epic Link\" = KISRMAC-2168 AND (created >= 2024-09-01 AND created <= 2025-09-01 OR resolved >= 2024-09-01 AND resolved <= 2025-09-01)"
# JQL = "project = AMT AND \"Epic Link\" in (AMT-19173, AMT-19175) AND issuetype in (Incident, Консультация, \"Исправление дефекта\", Инцидент, \"Incident OT\", Сопровождение, \"Мониторинг и безопасность\", Администрирование, \"Service request OT\") AND created >= 2024-09-01 AND created <= 2025-08-31 ORDER BY component DESC"
# JQL = "project = PRK AND issuetype in (Incident, Консультация, \"Исправление дефекта\", Инцидент, \"Incident OT\", Сопровождение, \"Мониторинг и безопасность\", Администрирование, \"Service request OT\") AND (created >= 2025-04-01 and created < 2025-09-01)"

CATEGORY_FINAL_COUNT = None
DATA_FOLDER = "classification_data"

# Настройки загрузки из JIRA
JIRA_CHUNK_SIZE = 50      # Размер порции для загрузки из JIRA (рекомендуется 25-100)
MAX_TASKS_LIMIT = None     # Лимит задач для тестирования (None = все)


# ===== НАСТРОЙКИ СОХРАНЕНИЯ ФАЙЛОВ =====
SAVE_TIMESTAMPED_FILES = False  # True - сохранять файлы с временными метками, False - только основные файлы

# ===== НАСТРОЙКИ МНОГОПОТОЧНОСТИ СУММАРИЗАЦИИ=====
SUMMARIZATION_THREADS = 10  # Количество потоков для суммаризации (рекомендуется 3-5)
SUMMARIZATION_RETRIES = 3  # Количество повторных попыток при ошибке

# Настройки для генерации категорий
CATEGORY_GENERATION_THREADS = 10  # Количество потоков для генерации категорий (рекомендуется 2-3)
CATEGORY_GENERATION_BATCH_SIZE = 5  # Размер батча задач для обработки (рекомендуется 3-10)
CATEGORY_GENERATION_RETRIES = 3  # Количество повторных попыток при ошибке
CATEGORY_GENERATION_PROMPT = None  # Название промпта (None = активный): "basic_v1", "detailed_v1", "technical_focus", "business_focus"

# Настройки для консолидации категорий
CATEGORY_CONSOLIDATION_PROMPT = None  # Название промпта (None = активный): "basic_v1", "detailed_v1", "technical_focus", "business_focus"
USE_ITERATIVE_CONSOLIDATION = False  # Использовать поэтапную консолидацию
CONSOLIDATION_REDUCTION_PERCENT = 30  # Процент уменьшения на каждой итерации (20-50)

# Настройки для классификации задач
CLASSIFICATION_THREADS = 100  # Количество потоков для классификации (рекомендуется 3-7)
CLASSIFICATION_MODE = "single"  # "single" - по одной задаче (точнее), "batch" - батчами (быстрее)
CLASSIFICATION_BATCH_SIZE = 15  # В режиме batch - Размер батча для классификации LLM (меньше = точнее)
CLASSIFICATION_RETRIES = 3  # Количество повторных попыток при ошибке


# ===== КОНФИГУРАЦИЯ ЭТАПОВ PIPELINE =====
# Настройте какие этапы выполнять (True/False)
PIPELINE_STEPS = {
    'fetch_tasks': False,        # Получение задач из JIRA
    'summarize_tasks': False,    # Суммаризация задач (новый этап)
    'generate_categories': False, # Генерация категорий
    'consolidate_categories': False, # Консолидация категорий
    'classify_tasks': True      # Классификация задач
}



def extract_project_from_jql(jql_query):
    """
    Извлекает название проекта из JQL запроса
    
    Args:
        jql_query (str): JQL запрос
    
    Returns:
        str: название проекта
    
    Raises:
        ValueError: если проект не указан в JQL запросе
    """
    if not jql_query:
        raise ValueError("JQL запрос пустой")
    
    # Ищем project = "PROJECT_NAME" или project in ("PROJ1", "PROJ2") или project = PROJECT_NAME
    project_patterns = [
        r'project\s*=\s*"([^"]+)"',  # project = "PROJECT_NAME"
        r'project\s*=\s*([A-Z][A-Z0-9_]+)',  # project = PROJECT_NAME
        r'project\s*in\s*\(\s*"([^"]+)"',  # project in ("PROJECT_NAME", ...)
        r'project\s*in\s*\(\s*([A-Z][A-Z0-9_]+)'  # project in (PROJECT_NAME, ...)
    ]
    
    for pattern in project_patterns:
        match = re.search(pattern, jql_query, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    
    raise ValueError(f"❌ Проект не найден в JQL запросе: {jql_query}")


def get_project_data_folder(jql_query, base_data_folder):
    """
    Определяет папку для сохранения данных проекта на основе JQL запроса
    
    Args:
        jql_query (str): JQL запрос
        base_data_folder (str): базовая папка для данных
    
    Returns:
        tuple: (project_name, project_folder_path)
    
    Raises:
        ValueError: если проект не найден в JQL запросе
    """
    project_name = extract_project_from_jql(jql_query)
    project_folder = f"{base_data_folder}/{project_name}"
    return project_name, project_folder


def main():
    """Основная функция запуска процесса классификации"""
    
    print("🚀 Запуск процесса классификации JIRA задач")
    print("=" * 50)
    
    # Показываем конфигурацию этапов
    print("\n⚙️ КОНФИГУРАЦИЯ ЭТАПОВ:")
    for step, enabled in PIPELINE_STEPS.items():
        status = "✅ Включен" if enabled else "❌ Отключен"
        print(f"   {step}: {status}")
    
    # Определяем папку проекта из JQL запроса
    try:
        project_name, project_folder = get_project_data_folder(JQL, DATA_FOLDER)
        print(f"\n🎯 Проект: {project_name}")
        print(f"📁 Папка проекта: {project_folder}")
        
        # Обновляем DATA_FOLDER для использования папки проекта
        DATA_FOLDER_PROJECT = project_folder
        
    except ValueError as e:
        print(f"❌ Ошибка конфигурации: {e}")
        return
    
    # Переменные для передачи данных между этапами
    tasks_df = None
    tasks_file = None
    summarized_df = None
    summarized_file = None
    categories_df = None
    categories_file = None
    final_categories_df = None
    final_file = None
    
    # Этап 1: Получение задач из JIRA
    if PIPELINE_STEPS['fetch_tasks']:
        print("\n📋 ЭТАП 1: Получение задач из JIRA")
        tasks_df, tasks_file = fetch_and_save_tasks(
            jql_query=JQL,
            data_folder=DATA_FOLDER_PROJECT,
            chunk_size=JIRA_CHUNK_SIZE,
            max_results=MAX_TASKS_LIMIT,
            save_timestamped=SAVE_TIMESTAMPED_FILES
        )
    else:
        print("\n⏭️ ЭТАП 1: Получение задач из JIRA - ПРОПУЩЕН")
        print("   📂 Попытка загрузить существующие задачи...")
        
        # Пытаемся загрузить существующие задачи из файла
        tasks_file = os.path.join(DATA_FOLDER_PROJECT, "tasks.xlsx")
        if os.path.exists(tasks_file):
            try:
                tasks_df = pd.read_excel(tasks_file)
                print(f"   ✅ Загружено {len(tasks_df)} задач из файла: {tasks_file}")
            except Exception as e:
                print(f"   ❌ Ошибка загрузки файла {tasks_file}: {e}")
                return
        else:
            print(f"   ❌ Файл с задачами не найден: {tasks_file}")
            print("   💡 Сначала запустите этап fetch_tasks или поместите файл tasks.xlsx в папку проекта")
            return
    
    # Этап 2: Суммаризация задач (НОВЫЙ)
    if PIPELINE_STEPS['summarize_tasks']:
        print("\n📝 ЭТАП 2: Суммаризация задач")
        summarized_df, summarized_file = summarize_tasks(
            tasks_df=tasks_df,
            project_folder=DATA_FOLDER_PROJECT,
            save_timestamped=SAVE_TIMESTAMPED_FILES,
            max_workers=SUMMARIZATION_THREADS,
            max_retries=SUMMARIZATION_RETRIES
        )
        # Используем суммаризированные данные для дальнейшей обработки
        working_df = summarized_df
    else:
        print("\n⏭️ ЭТАП 2: Суммаризация задач - ПРОПУЩЕН")
        print("   📂 Попытка загрузить существующие суммаризированные задачи...")
        
        # Пытаемся загрузить существующие суммаризированные задачи
        summary_file = os.path.join(DATA_FOLDER_PROJECT, "tasks_summary.xlsx")
        if os.path.exists(summary_file):
            try:
                working_df = pd.read_excel(summary_file)
                print(f"   ✅ Загружено {len(working_df)} суммаризированных задач из файла: {summary_file}")
            except Exception as e:
                print(f"   ⚠️ Ошибка загрузки суммаризированных задач: {e}")
                print("   📋 Используем исходные задачи без суммаризации")
                working_df = tasks_df
        else:
            print("   📋 Файл с суммаризированными задачами не найден, используем исходные задачи")
            working_df = tasks_df
    
    # Этап 3: Генерация категорий
    if PIPELINE_STEPS['generate_categories']:
        print("\n🤖 ЭТАП 3: Генерация категорий")
        categories_df, categories_file = generate_categories_from_tasks(
            tasks_df=working_df,
            batch_size=CATEGORY_GENERATION_BATCH_SIZE,
            data_folder=DATA_FOLDER_PROJECT,
            save_timestamped=SAVE_TIMESTAMPED_FILES,
            max_workers=CATEGORY_GENERATION_THREADS,
            max_retries=CATEGORY_GENERATION_RETRIES,
            prompt_name=CATEGORY_GENERATION_PROMPT
        )
    else:
        print("\n⏭️ ЭТАП 3: Генерация категорий - ПРОПУЩЕН")
        print("   📂 Попытка загрузить существующие категории...")
        
        # Пытаемся загрузить существующие категории
        categories_file = os.path.join(DATA_FOLDER_PROJECT, "categories.xlsx")
        if os.path.exists(categories_file):
            try:
                categories_df = pd.read_excel(categories_file)
                print(f"   ✅ Загружено {len(categories_df)} категорий из файла: {categories_file}")
            except Exception as e:
                print(f"   ❌ Ошибка загрузки категорий: {e}")
                categories_df = None
        else:
            print("   ⚠️ Файл с категориями не найден")
            categories_df = None
    
    # Этап 4: Создание финального списка категорий
    if PIPELINE_STEPS['consolidate_categories'] and categories_df is not None:
        print("\n🎯 ЭТАП 4: Консолидация категорий")
        final_categories_df, final_file = create_final_categories(
            categories_df=categories_df,
            target_count=CATEGORY_FINAL_COUNT,
            data_folder=DATA_FOLDER_PROJECT,
            save_timestamped=SAVE_TIMESTAMPED_FILES,
            prompt_name=CATEGORY_CONSOLIDATION_PROMPT,
            use_iterative=USE_ITERATIVE_CONSOLIDATION,
            reduction_percent=CONSOLIDATION_REDUCTION_PERCENT
        )
    else:
        print("\n⏭️ ЭТАП 4: Консолидация категорий - ПРОПУЩЕН")
    
    # Этап 5: Классификация задач по финальным категориям
    if PIPELINE_STEPS['classify_tasks']:
        print("\n🏷️ ЭТАП 5: Присвоение категорий задачам")
        classified_df, classified_file = classify_all_tasks(
            tasks_df=working_df,
            categories_df=final_categories_df,
            batch_size=CLASSIFICATION_BATCH_SIZE,
            data_folder=DATA_FOLDER_PROJECT,
            save_timestamped=SAVE_TIMESTAMPED_FILES,
            max_workers=CLASSIFICATION_THREADS,
            classification_mode=CLASSIFICATION_MODE,
            max_retries=CLASSIFICATION_RETRIES
        )
    else:
        print("\n⏭️ ЭТАП 5: Присвоение категорий задачам - ПРОПУЩЕН")
    
    # Итоговая сводка
    print("\n" + "=" * 50)
    print("✅ ПРОЦЕСС ЗАВЕРШЕН")
    
    # Статистика по данным
    if tasks_df is not None:
        print(f"📊 Обработано задач: {len(tasks_df)}")
    if categories_df is not None:
        print(f"🏷️ Создано категорий: {len(categories_df)}")
    if final_categories_df is not None:
        print(f"🎯 Финальных категорий: {len(final_categories_df)}")
    
    # Статистика по классификации
    try:
        if 'classified_df' in locals() and classified_df is not None:
            classified_count = (classified_df['assigned_category'] != '').sum()
            print(f"📋 Классифицировано задач: {classified_count}")
    except:
        pass
    
    # Список созданных файлов
    print("\n📁 Созданные файлы:")
    if tasks_file:
        print(f"   📄 Задачи: {tasks_file}")
    if 'summarized_file' in locals() and summarized_file:
        print(f"   📄 Суммаризированные задачи: {summarized_file}")
    if categories_file:
        print(f"   📄 Категории: {categories_file}")
    if 'final_file' in locals() and final_file:
        print(f"   📄 Финальные категории: {final_file}")
    if 'classified_file' in locals() and classified_file:
        print(f"   📄 Классифицированные задачи: {classified_file}")
    
    print("\n💡 Для тестирования отдельных этапов измените PIPELINE_STEPS в конфигурации")


if __name__ == "__main__":
    main()