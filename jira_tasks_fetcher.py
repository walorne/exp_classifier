"""
Модуль для получения задач из JIRA и сохранения в Excel
"""
import pandas as pd
import os
import re
from datetime import datetime
from clients.jira_client import get_jira_client


def clean_description(desc):
    """Очистка описания от лишних символов и форматирования"""
    if not desc:
        return ''
    
    # Удаляем переносы строк и лишние пробелы
    desc = desc.replace('\n', ' ').replace('\r', ' ')
    desc = ' '.join(desc.split())  # Убираем множественные пробелы
    
    # Удаляем JIRA разметку
    desc = re.sub(r'\{[^}]*\}', '', desc)  # {code}, {quote}, etc.
    desc = re.sub(r'\[[^\]]*\]', '', desc)  # [~username], [link]
    desc = re.sub(r'h[1-6]\.\s*', '', desc)  # h1. h2. заголовки
    desc = re.sub(r'\*[^*]*\*', '', desc)  # *жирный текст*
    desc = re.sub(r'_[^_]*_', '', desc)  # _курсив_
    
    # Убираем URL
    desc = re.sub(r'https?://\S+', '', desc)
    
    # Убираем лишние символы
    desc = re.sub(r'[^\w\s\-.,!?()]', ' ', desc, flags=re.UNICODE)
    
    # Финальная очистка пробелов
    desc = ' '.join(desc.split())
    
    return desc


def fetch_and_save_tasks(jql_query, data_folder="classification_data", chunk_size=100, max_results=None):
    """
    Получает задачи из JIRA по JQL запросу частями и сохраняет в Excel
    
    ОПТИМИЗАЦИИ:
    - Загрузка порциями (chunk_size) вместо всех задач сразу
    - Запрос только нужных полей: key, summary, description, issuetype, timespent
    - Быстрый подсчет общего количества с минимальными полями
    
    Args:
        jql_query (str): JQL запрос для получения задач
        data_folder (str): папка для сохранения файлов
        chunk_size (int): размер порции для загрузки (по умолчанию 100)
        max_results (int): максимальное количество задач (None = все)
    
    Returns:
        pd.DataFrame: DataFrame с задачами
        str: путь к основному файлу задач
    """
    print(f"🔍 Выполняю JQL запрос частями по {chunk_size} задач...")
    
    # Подключаемся к JIRA
    jira = get_jira_client()
    
    # Сначала узнаем общее количество задач (быстрый запрос без полей)
    try:
        total_count = jira.search_issues(jql_query, maxResults=0, fields='key').total
        print(f"📊 Всего найдено задач: {total_count}")
        
        if max_results and max_results < total_count:
            total_count = max_results
            print(f"🎯 Ограничиваем до: {max_results} задач")
            
    except Exception as e:
        print(f"⚠️ Не удалось получить общее количество: {e}")
        print("Продолжаем загрузку порциями...")
        total_count = None
    
    # Загружаем задачи порциями
    all_data = []
    start_at = 0
    chunk_num = 1
    
    while True:
        try:
            print(f"🔄 Загружаю порцию {chunk_num} (задачи {start_at + 1}-{start_at + chunk_size})...")
            
            # Ограничиваем размер порции если приближаемся к лимиту
            current_chunk_size = chunk_size
            if max_results and start_at + chunk_size > max_results:
                current_chunk_size = max_results - start_at
                
            if current_chunk_size <= 0:
                break
                
            # Загружаем порцию только с нужными полями (для скорости)
            issues = jira.search_issues(
                jql_query, 
                startAt=start_at, 
                maxResults=current_chunk_size,
                fields='key,summary,description,issuetype,timespent'  # 🔥 ТОЛЬКО НУЖНЫЕ ПОЛЯ
            )
            
            if not issues:
                print("✅ Больше задач не найдено")
                break
                
            print(f"   📥 Получено {len(issues)} задач")
            
            # Обрабатываем задачи из текущей порции
            for issue in issues:
                all_data.append({
                    'key': issue.key,
                    'title': issue.fields.summary,
                    'description': clean_description(issue.fields.description),
                    'issuetype': issue.fields.issuetype.name,
                    'time_spent': getattr(issue.fields, 'timespent', 0) or 0,
                    'processing_stage': 'new',  # Этап обработки
                    'category_id': '',          # ID категории (пока пустой)
                    'batch_processed': 0        # Номер батча обработки
                })
            
            # Переходим к следующей порции
            start_at += len(issues)
            chunk_num += 1
            
            # Если получили меньше задач чем запрашивали - это последняя порция
            if len(issues) < current_chunk_size:
                print("✅ Достигнут конец результатов")
                break
                
            # Если достигли лимита
            if max_results and start_at >= max_results:
                print(f"✅ Достигнут лимит: {max_results} задач")
                break
                
        except Exception as e:
            print(f"❌ Ошибка при загрузке порции {chunk_num}: {e}")
            if "401" in str(e):
                print("💡 Проблема с аутентификацией - проверьте токен!")
                raise
            break

    if not all_data:
        print("❌ Не удалось загрузить ни одной задачи!")
        raise Exception("Нет данных для обработки")

    df = pd.DataFrame(all_data)
    print(f"📊 Итого загружено: {len(df)} задач")
    
    # Создаем папку для данных
    os.makedirs(data_folder, exist_ok=True)

    # Сохраняем задачи в Excel
    main_tasks_file = os.path.join(data_folder, "tasks.xlsx")
    df.to_excel(main_tasks_file, index=False, sheet_name='Tasks')
    print(f"✅ Основной файл задач: {main_tasks_file}")
    
    return df, main_tasks_file
