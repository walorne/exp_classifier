"""
Скрипт только для классификации задач (если категории уже созданы)
"""
from task_classifier import main_classification

if __name__ == "__main__":
    print("🏷️ Запуск классификации задач по готовым категориям...")
    print("=" * 50)
    
    classified_df, results_file = main_classification()
    
    if classified_df is not None:
        print("\n🎉 Готово! Проверьте файл с результатами.")
    else:
        print("\n❌ Классификация не выполнена.")
