"""
Модуль для консолидации категорий в финальный список
"""
import pandas as pd
import os
from datetime import datetime
from clients.ai_client import create_default_client
from utils.file_utils import safe_save_excel


def consolidate_categories(categories_df, target_count, llm_client):
    """Консолидирует категории до целевого количества"""
    
    # Подготавливаем данные для модели
    categories_text = ""
    for idx, row in categories_df.iterrows():
        categories_text += f"{idx+1}. {row['Название']}: {row['Описание']}\n"
    
    prompt = f"""Ты эксперт по анализации и структурированию данных. У тебя есть список категорий для классификации IT-задач.

ТВОЯ ЗАДАЧА:
1. Проанализируй все категории и найди похожие по смыслу
2. Объедини похожие категории в одну
3. Создай ровно {target_count} итоговых категорий
4. НЕЛЬЗЯ удалять категории - только объединять!

ИСХОДНЫЕ КАТЕГОРИИ:
{categories_text}

ПРАВИЛА ОБЪЕДИНЕНИЯ:
- Название новой категории должно отражать суть ВСЕХ объединенных категорий
- Описание должно включать все аспекты объединенных категорий
- Если категории нельзя объединить - оставь их как есть
- Результат должен содержать ровно {target_count} категорий

ВЕРНИ РЕЗУЛЬТАТ СТРОГО В ФОРМАТЕ CSV (разделитель - точка с запятой):
Название;Описание

Пример:
API и интеграции;Разработка, настройка и поддержка API интеграций, веб-сервисов и внешних подключений
Исправление ошибок и багов;Анализ, диагностика и устранение ошибок в системе, отладка и тестирование исправлений

ВАЖНО:
- НЕ добавляй заголовки столбцов
- НЕ добавляй номера строк  
- Каждая категория на новой строке
- Используй точку с запятой как разделитель
- Ровно {target_count} строк в ответе"""

    print(f"🔄 Консолидирую {len(categories_df)} категорий в {target_count}...")
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


def create_final_categories(categories_df, target_count, data_folder="classification_data", save_timestamped=True):
    """
    Создает финальный список категорий
    
    Args:
        categories_df (pd.DataFrame): DataFrame с исходными категориями
        target_count (int): целевое количество категорий
        data_folder (str): папка для сохранения файлов
    
    Returns:
        pd.DataFrame: DataFrame с финальными категориями
        str: путь к основному файлу финальных категорий
    """
    print(f"\n🎯 Создание финального списка категорий...")
    
    # Создаем LLM клиент
    llm_client = create_default_client()
    
    # Консолидация категорий
    if len(categories_df) > target_count:
        print(f"📊 Консолидация: {len(categories_df)} → {target_count} категорий")
        
        try:
            consolidated_response = consolidate_categories(categories_df, target_count, llm_client)
            consolidated_categories = parse_consolidated_categories(consolidated_response)
            
            if len(consolidated_categories) == target_count:
                # Создаем DataFrame с консолидированными категориями
                final_categories_df = pd.DataFrame(consolidated_categories)
                
                print(f"✅ Консолидация завершена: {len(final_categories_df)} категорий")
                print("\n📋 ИТОГОВЫЕ КАТЕГОРИИ:")
                for idx, row in final_categories_df.iterrows():
                    print(f"{idx+1}. {row['Название']}")
                
            else:
                print(f"⚠️ Получено {len(consolidated_categories)} категорий вместо {target_count}")
                print("Используем исходные категории")
                final_categories_df = categories_df.copy()
                
        except Exception as e:
            print(f"❌ Ошибка при консолидации: {e}")
            print("Используем исходные категории")
            final_categories_df = categories_df.copy()
    else:
        print(f"✅ Категорий уже {len(categories_df)} - консолидация не требуется")
        final_categories_df = categories_df.copy()
    
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
