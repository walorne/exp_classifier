"""
Модуль для консолидации категорий в финальный список
Версия 0.3 - с поддержкой настраиваемых промптов
"""
import pandas as pd
import os
from datetime import datetime
from clients.ai_client import create_default_client
from utils.file_utils import safe_save_excel
from prompts.prompt_manager import create_category_prompt_manager


def consolidate_categories(categories_df, target_count, llm_client, prompt_name=None):
    """
    Консолидирует категории до целевого количества
    
    Args:
        categories_df: DataFrame с категориями
        target_count: целевое количество категорий
        llm_client: клиент для LLM
        prompt_name: название промпта (если None, используется активный)
    """
    
    # Создаем менеджер промптов
    prompt_manager = create_category_prompt_manager()
    
    # Подготавливаем данные для модели
    categories_text = ""
    for idx, row in categories_df.iterrows():
        keywords = row.get('Ключевые_слова', '') if pd.notna(row.get('Ключевые_слова', '')) else ''
        task_types = row.get('Типы_задач', '') if pd.notna(row.get('Типы_задач', '')) else ''
        
        categories_text += f"{idx+1}. {row['Название']}: {row['Описание']}"
        if keywords:
            categories_text += f" | Ключевые слова: {keywords}"
        if task_types:
            categories_text += f" | Типы задач: {task_types}"
        categories_text += "\n"
    
    # Форматируем промпт с помощью менеджера
    prompt = prompt_manager.format_category_consolidation_prompt(
        categories_text=categories_text,
        target_count=target_count,
        prompt_name=prompt_name
    )

    print(f"🔄 Консолидирую {len(categories_df)} категорий в {target_count}...")
    if prompt_name:
        print(f"📝 Используется промпт: {prompt_name}")
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


def consolidate_categories_iteratively(categories_df, target_count, llm_client, prompt_name=None, reduction_percent=30, max_iterations=5):
    """
    Поэтапная консолидация категорий с постепенным уменьшением количества
    
    Args:
        categories_df: DataFrame с исходными категориями
        target_count: целевое количество категорий
        llm_client: клиент для LLM
        prompt_name: название промпта
        reduction_percent: процент уменьшения на каждой итерации (по умолчанию 30%)
        max_iterations: максимальное количество итераций
    
    Returns:
        pd.DataFrame: консолидированные категории
    """
    current_categories = categories_df.copy()
    iteration = 0
    
    print(f"🔄 Начинаем поэтапную консолидацию...")
    print(f"   Исходное количество: {len(current_categories)}")
    print(f"   Целевое количество: {target_count}")
    print(f"   Процент уменьшения: {reduction_percent}%")
    print(f"   Максимум итераций: {max_iterations}")
    
    while len(current_categories) > target_count and iteration < max_iterations:
        iteration += 1
        
        # Вычисляем целевое количество для текущей итерации
        if iteration == max_iterations:
            # На последней итерации стремимся к финальному количеству
            current_target = target_count
        else:
            # Вычисляем количество для уменьшения на заданный процент
            reduction = max(1, int(len(current_categories) * reduction_percent / 100))
            current_target = len(current_categories) - reduction
            # НИКОГДА не увеличиваем количество категорий!
            current_target = min(current_target, len(current_categories))
            # И не опускаемся ниже целевого количества
            current_target = max(target_count, current_target)
        
        print(f"\n📊 Итерация {iteration}: {len(current_categories)} → {current_target} категорий")
        
        try:
            # Выполняем консолидацию
            consolidated_response = consolidate_categories(current_categories, current_target, llm_client, prompt_name)
            consolidated_categories = parse_consolidated_categories(consolidated_response)
            
            if len(consolidated_categories) > 0:
                current_categories = pd.DataFrame(consolidated_categories)
                print(f"✅ Итерация {iteration} завершена: получено {len(current_categories)} категорий")
                
                # Показываем прогресс
                progress = ((len(categories_df) - len(current_categories)) / (len(categories_df) - target_count)) * 100
                print(f"   📈 Прогресс: {progress:.1f}%")
                
            else:
                print(f"❌ Итерация {iteration}: LLM не вернул категории")
                break
                
        except Exception as e:
            print(f"❌ Ошибка на итерации {iteration}: {e}")
            break
    
    if len(current_categories) <= target_count:
        print(f"\n🎉 Поэтапная консолидация завершена успешно!")
        print(f"   Финальное количество: {len(current_categories)} категорий")
    else:
        print(f"\n⚠️ Поэтапная консолидация завершена с ограничениями")
        print(f"   Финальное количество: {len(current_categories)} категорий (целевое: {target_count})")
    
    return current_categories


def create_final_categories(categories_df, target_count, data_folder="classification_data", save_timestamped=True, prompt_name=None, use_iterative=True, reduction_percent=30):
    """
    Создает финальный список категорий
    
    Args:
        categories_df (pd.DataFrame): DataFrame с исходными категориями
        target_count (int): целевое количество категорий
        data_folder (str): папка для сохранения файлов
        save_timestamped (bool): сохранять ли файл с таймстампом
        prompt_name (str): название промпта для консолидации (если None, используется активный)
        use_iterative (bool): использовать ли поэтапную консолидацию
        reduction_percent (int): процент уменьшения на каждой итерации (если use_iterative=True)
    
    Returns:
        pd.DataFrame: DataFrame с финальными категориями
        str: путь к основному файлу финальных категорий
    """
    print(f"\n🎯 Создание финального списка категорий...")
    
    # Создаем LLM клиент
    llm_client = create_default_client()
    
    # ВРЕМЕННО ОТКЛЮЧАЕМ ПОЭТАПНУЮ КОНСОЛИДАЦИЮ - ОНА СЛОМАНА!
    print(f"📊 Используем одноэтапную консолидацию: {len(categories_df)} → {target_count} категорий")
    try:
        consolidated_response = consolidate_categories(categories_df, target_count, llm_client, prompt_name)
        consolidated_categories = parse_consolidated_categories(consolidated_response)
        
        if len(consolidated_categories) > 0:
            final_categories_df = pd.DataFrame(consolidated_categories)
            print(f"✅ Консолидация завершена: {len(final_categories_df)} категорий")
        else:
            print(f"❌ LLM не вернул ни одной категории")
            final_categories_df = pd.DataFrame(columns=['Название', 'Описание'])
            
    except Exception as e:
        print(f"❌ Ошибка при консолидации: {e}")
        final_categories_df = pd.DataFrame(columns=['Название', 'Описание'])
    
    # Показываем итоговые категории
    if len(final_categories_df) > 0:
        print("\n📋 ИТОГОВЫЕ КАТЕГОРИИ:")
        for idx, row in final_categories_df.iterrows():
            print(f"{idx+1}. {row['Название']}")
    else:
        print("\n❌ Итоговые категории не созданы")
    
    # Сохраняем консолидированные категории с безопасной обработкой
    print(f"\n💾 Сохраняю итоговые категории в файл...")
    
    # Основной файл итоговых категорий
    main_final_file = os.path.join(data_folder, "final_categories.xlsx")
    success = safe_save_excel(final_categories_df, main_final_file, 'Final_Categories')
    
    if success:
        print(f"✅ Файл успешно сохранен: {main_final_file}")
    else:
        print(f"❌ Не удалось сохранить итоговые категории: {main_final_file}")
        return final_categories_df, None
    
    return final_categories_df, main_final_file


def main():
    """
    Основная функция для тестирования консолидации категорий
    Позволяет запускать скрипт напрямую для экспериментов
    """
    print("🧪 Тестирование консолидации категорий")
    print("=" * 50)
    
    # Конфигурация для тестирования
    DATA_FOLDER = "classification_data/MPSM"
    TARGET_COUNT = 15
    USE_ITERATIVE = True
    REDUCTION_PERCENT = 30
    PROMPT_NAME = None  # None = активный промпт
    
    # Пытаемся найти файл с категориями
    categories_file = os.path.join(DATA_FOLDER, "categories.xlsx")
    
    if not os.path.exists(categories_file):
        print(f"❌ Файл с категориями не найден: {categories_file}")
        print("💡 Поместите файл categories.xlsx в папку classification_data и запустите скрипт снова")
        return
    
    print(f"📂 Загружаем категории из файла: {categories_file}")
    try:
        categories_df = pd.read_excel(categories_file)
        print(f"✅ Загружено {len(categories_df)} категорий")
    except Exception as e:
        print(f"❌ Ошибка загрузки файла: {e}")
        return
    
    # Показываем исходные категории
    print(f"\n📋 ИСХОДНЫЕ КАТЕГОРИИ ({len(categories_df)}):")
    for idx, row in categories_df.iterrows():
        print(f"{idx+1:2d}. {row['Название']}")
    
    # Настройки консолидации
    print(f"\n⚙️ НАСТРОЙКИ КОНСОЛИДАЦИИ:")
    print(f"   Целевое количество: {TARGET_COUNT}")
    print(f"   Поэтапная консолидация: {'Да' if USE_ITERATIVE else 'Нет'}")
    if USE_ITERATIVE:
        print(f"   Процент уменьшения: {REDUCTION_PERCENT}%")
    print(f"   Промпт: {PROMPT_NAME or 'Активный'}")
    
    # Выполняем консолидацию
    try:
        final_categories_df, final_file = create_final_categories(
            categories_df=categories_df,
            target_count=TARGET_COUNT,
            data_folder=DATA_FOLDER,
            save_timestamped=False,
            prompt_name=PROMPT_NAME,
            use_iterative=USE_ITERATIVE,
            reduction_percent=REDUCTION_PERCENT
        )
        
        print(f"\n🎉 КОНСОЛИДАЦИЯ ЗАВЕРШЕНА!")
        print(f"   Исходное количество: {len(categories_df)}")
        print(f"   Финальное количество: {len(final_categories_df)}")
        print(f"   Файл сохранен: {final_file}")
        
    except Exception as e:
        print(f"\n❌ ОШИБКА ПРИ КОНСОЛИДАЦИИ: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()