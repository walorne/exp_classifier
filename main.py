"""
Основной скрипт для классификации JIRA задач
"""
from jira_tasks_fetcher import fetch_and_save_tasks
from category_generator import generate_categories_from_tasks
from category_consolidator import create_final_categories
from task_classifier import classify_all_tasks, load_tasks_and_categories

# ===== КОНФИГУРАЦИЯ СКРИПТА =====
JQL = "project = MPSM AND issueFunction in issuesInEpics(\"ERP_JOBs ~ '00-00377754#000000002'\") AND created >= 2024-09-01 ORDER BY created DESC"
CATEGORY_FINAL_COUNT = 10
BATCH_SIZE = 50
DATA_FOLDER = "classification_data"

# Настройки загрузки из JIRA
JIRA_CHUNK_SIZE = 50      # Размер порции для загрузки из JIRA
MAX_TASKS_LIMIT = None     # Лимит задач для тестирования (None = все)

# Настройки классификации
CLASSIFICATION_BATCH_SIZE = 15  # Размер батча для классификации LLM (меньше = точнее)


def main():
    """Основная функция запуска процесса классификации"""
    
    print("🚀 Запуск процесса классификации JIRA задач")
    print("=" * 50)
    
    # Этап 1: Получение задач из JIRA
    print("\n📋 ЭТАП 1: Получение задач из JIRA")
    tasks_df, tasks_file = fetch_and_save_tasks(
        jql_query=JQL,
        data_folder=DATA_FOLDER,
        chunk_size=JIRA_CHUNK_SIZE,
        max_results=MAX_TASKS_LIMIT
    )
    
    # Этап 2: Генерация категорий
    print("\n🤖 ЭТАП 2: Генерация категорий")
    categories_df, categories_file = generate_categories_from_tasks(
        tasks_df=tasks_df,
        batch_size=BATCH_SIZE,
        data_folder=DATA_FOLDER
    )
    
    # Этап 3: Создание финального списка категорий
    print("\n🎯 ЭТАП 3: Консолидация категорий")
    final_categories_df, final_file = create_final_categories(
        categories_df=categories_df,
        target_count=CATEGORY_FINAL_COUNT,
        data_folder=DATA_FOLDER
    )
    
    # Этап 4: Классификация задач по финальным категориям
    print("\n🏷️ ЭТАП 4: Присвоение категорий задачам")
    classified_df, classified_file = classify_all_tasks(
        tasks_df=tasks_df,
        categories_df=final_categories_df,
        batch_size=CLASSIFICATION_BATCH_SIZE,
        data_folder=DATA_FOLDER
    )
    
    # Итоговая сводка
    print("\n" + "=" * 50)
    print("✅ ПРОЦЕСС ЗАВЕРШЕН")
    print(f"📊 Обработано задач: {len(tasks_df)}")
    print(f"🏷️ Создано категорий: {len(categories_df)}")
    print(f"🎯 Финальных категорий: {len(final_categories_df)}")
    print(f"📋 Классифицировано задач: {(classified_df['assigned_category'] != '').sum()}")
    print("\n📁 Созданные файлы:")
    print(f"   📄 Задачи: {tasks_file}")
    print(f"   📄 Категории: {categories_file}")
    print(f"   📄 Финальные категории: {final_file}")
    print(f"   📄 Классифицированные задачи: {classified_file}")


if __name__ == "__main__":
    main()