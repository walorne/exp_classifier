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
        keywords = row.get('Ключевые_слова', '') if pd.notna(row.get('Ключевые_слова', '')) else ''
        task_types = row.get('Типы_задач', '') if pd.notna(row.get('Типы_задач', '')) else ''
        
        categories_text += f"{idx+1}. {row['Название']}: {row['Описание']}"
        if keywords:
            categories_text += f" | Ключевые слова: {keywords}"
        if task_types:
            categories_text += f" | Типы задач: {task_types}"
        categories_text += "\n"
    
    prompt = f"""Ты эксперт по анализации и структурированию IT-задач. У тебя есть список категорий для классификации задач разработки и поддержки.

ЭТАП 1 - АНАЛИЗ ИСХОДНЫХ ДАННЫХ:
1. Проанализируй ключевые слова всех категорий
2. Определи основные технические домены (UI/Frontend, API/Backend, Mobile, Data Processing)
3. Выяви бизнес-критичные области (авторизация, платежи, аналитика, навигация)
4. Учти типы задач и их распределение
5. Учти, что приведенные примеры это только примеры, не опирайся на них, принимай решения о категориях самостоятельно!!!

ЭТАП 2 - КОНСОЛИДАЦИЯ:
1. Объединяй категории ТОЛЬКО в рамках одного технического слоя
2. Сохраняй бизнес-критичные домены как отдельные категории
3. Создай ровно {target_count} итоговых категорий
4. НЕЛЬЗЯ удалять категории - только объединять!
5. Приоритизируй категории с большим количеством задач
6. Избегай пересечений между итоговыми категориями

ТЕХНИЧЕСКИЕ СЛОИ ДЛЯ ОБЪЕДИНЕНИЯ:
1. Frontend/UI слой: UI/UX задачи, отображение, интерфейс, визуальные элементы
2. Backend/API слой: серверная логика, API, интеграции, обработка запросов
3. Data слой: валидация данных, обработка, передача между системами
4. Mobile слой: специфика iOS/Android, мобильные функции
5. Analytics слой: события, метрики, отслеживание пользователей
6. Navigation слой: переходы, deeplink, маршрутизация
7. Auth/Security слой: авторизация, безопасность, управление аккаунтами
8. Payment слой: платежи, финансовые операции, бонусы

Эти слои содержат примеры, не опирайся на них, принимай решения о категориях самостоятельно!!!

ПРИМЕРЫ ПРАВИЛЬНОГО ОБЪЕДИНЕНИЯ:
✅ "UI/UX Корректировки" + "Визуальные дефекты" + "Улучшение UX/UI" → "Frontend и UI исправления"
✅ "Интеграция API" + "API ошибки" + "Backend логика" → "Backend и API интеграции"
✅ "Валидация данных" + "Обработка данных" → "Обработка и валидация данных"
эти примеры можно использовать как примеры, но не опирайся на них, принимай решения о категориях самостоятельно!!!

ПРИМЕРЫ НЕПРАВИЛЬНОГО ОБЪЕДИНЕНИЯ:
❌ "UI исправления" + "API ошибки" (разные технические слои)
❌ "Мобильная разработка" + "Веб-интерфейс" (разные платформы)
❌ Создание категории "Разработка ПО" (слишком общая)


ИСХОДНЫЕ КАТЕГОРИИ:
{categories_text}

ПРАВИЛА ОБЪЕДИНЕНИЯ:
- Объединяй ТОЛЬКО категории из одного технического слоя
- Название новой категории должно четко отражать технический домен
- Описание должно включать все ключевые аспекты объединенных категорий
- Используй терминологию из исходных ключевых слов
- Сохраняй бизнес-критичные категории (авторизация, платежи, навигация)
- Результат должен содержать ровно {target_count} категорий
- Каждая итоговая категория должна быть уникальной и не пересекаться с другими

ОБЯЗАТЕЛЬНЫЕ КАТЕГОРИИ К СОХРАНЕНИЮ:
- Авторизация и управление аккаунтами
- Платежи и финансовые операции  
- Навигация и deeplink обработка
- Валидация и обработка данных
- Аналитика и события

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
