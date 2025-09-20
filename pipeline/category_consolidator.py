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


def create_final_categories(categories_df, target_count, data_folder="classification_data", save_timestamped=True, prompt_name=None):
    """
    Создает финальный список категорий
    
    Args:
        categories_df (pd.DataFrame): DataFrame с исходными категориями
        target_count (int): целевое количество категорий
        data_folder (str): папка для сохранения файлов
        save_timestamped (bool): сохранять ли файл с таймстампом
        prompt_name (str): название промпта для консолидации (если None, используется активный)
    
    Returns:
        pd.DataFrame: DataFrame с финальными категориями
        str: путь к основному файлу финальных категорий
    """
    print(f"\n🎯 Создание финального списка категорий...")
    
    # Создаем LLM клиент
    llm_client = create_default_client()
    
    # Всегда выполняем консолидацию
    print(f"📊 Консолидация: {len(categories_df)} → {target_count} категорий")
    
    try:
        consolidated_response = consolidate_categories(categories_df, target_count, llm_client, prompt_name)
        consolidated_categories = parse_consolidated_categories(consolidated_response)
        
        # Всегда используем результат консолидации
        if len(consolidated_categories) > 0:
            # Создаем DataFrame с консолидированными категориями
            final_categories_df = pd.DataFrame(consolidated_categories)
            
            if len(consolidated_categories) == target_count:
                print(f"✅ Консолидация завершена: {len(final_categories_df)} категорий (точно как запрошено)")
            else:
                print(f"✅ Консолидация завершена: {len(final_categories_df)} категорий (целевое было: {target_count})")
                
            print("\n📋 ИТОГОВЫЕ КАТЕГОРИИ:")
            for idx, row in final_categories_df.iterrows():
                print(f"{idx+1}. {row['Название']}")
            
        else:
            print(f"❌ LLM не вернул ни одной категории - это ошибка парсинга")
            print("Создаем пустой DataFrame")
            final_categories_df = pd.DataFrame(columns=['Название', 'Описание'])
            
    except Exception as e:
        print(f"❌ Ошибка при консолидации: {e}")
        print("Создаем пустой DataFrame - консолидация не удалась")
        final_categories_df = pd.DataFrame(columns=['Название', 'Описание'])
    
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
