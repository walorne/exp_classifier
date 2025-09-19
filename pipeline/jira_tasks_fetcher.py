"""
Модуль для получения задач из JIRA и сохранения в Excel
"""
import pandas as pd
import os
import re
from datetime import datetime
from clients.jira_client import get_jira_client
from utils.file_utils import safe_save_excel


def clean_text(text):
    """Очистка текста от лишних символов и форматирования"""
    if not text:
        return ''
    
    # Удаляем переносы строк и лишние пробелы
    text = text.replace('\n', ' ').replace('\r', ' ')
    text = ' '.join(text.split())  # Убираем множественные пробелы
    
    # Удаляем JIRA разметку (более точно)
    text = re.sub(r'\{code[^}]*\}.*?\{code\}', '', text, flags=re.DOTALL)  # {code}...{code}
    text = re.sub(r'\{quote[^}]*\}.*?\{quote\}', '', text, flags=re.DOTALL)  # {quote}...{quote}
    text = re.sub(r'\{noformat[^}]*\}.*?\{noformat\}', '', text, flags=re.DOTALL)  # {noformat}
    text = re.sub(r'\[~[^\]]+\]', '', text)  # [~username] - упоминания пользователей
    text = re.sub(r'\[[^\]]*\|[^\]]*\]', '', text)  # [text|link] - ссылки с текстом
    text = re.sub(r'h[1-6]\.\s+', '', text)  # h1. h2. заголовки
    
    # Убираем JIRA форматирование, но сохраняем содержимое
    text = re.sub(r'\*([^*]+)\*', r'\1', text)  # *жирный* → жирный
    text = re.sub(r'_([^_]+)_', r'\1', text)  # _курсив_ → курсив
    
    # Убираем URL
    text = re.sub(r'https?://[^\s]+', '', text)
    
    # Убираем только действительно лишние символы, сохраняя важную пунктуацию
    # Оставляем: буквы, цифры, пробелы, основную пунктуацию, скобки, кавычки
    text = re.sub(r'[^\w\s\-.,!?():;"\'@#№%/\\]', ' ', text, flags=re.UNICODE)
    
    # Финальная очистка пробелов
    text = ' '.join(text.split())
    
    return text


def clean_description(desc):
    """Очистка описания от лишних символов и форматирования"""
    return clean_text(desc)


def collect_and_clean_comments(issue):
    """
    Собирает все комментарии к задаче и объединяет их в один очищенный текст
    
    Args:
        issue: объект задачи JIRA
    
    Returns:
        str: объединенный и очищенный текст всех комментариев
    """
    if not hasattr(issue.fields, 'comment') or not issue.fields.comment:
        return ''
    
    comments_text = []
    
    try:
        # Получаем все комментарии
        comments = issue.fields.comment.comments
        
        for comment in comments:
            if hasattr(comment, 'body') and comment.body:
                # Очищаем текст комментария
                clean_comment = clean_text(comment.body)
                if clean_comment.strip():  # Добавляем только непустые комментарии
                    comments_text.append(clean_comment)
        
        # Объединяем все комментарии через разделитель
        if comments_text:
            return ' | '.join(comments_text)
        else:
            return ''
            
    except Exception as e:
        print(f"⚠️ Ошибка при обработке комментариев для {issue.key}: {e}")
        return ''


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
        print(f"⚠️ Ошибка при подсчете задач: {e}")
        if "401" in str(e) or "Unauthorized" in str(e):
            print("🔐 Проблема с аутентификацией JIRA:")
            print("   - Проверьте JIRA_TOKEN в файле .env")
            print("   - Убедитесь что токен действителен")
            print("   - Проверьте права доступа к проекту")
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
                fields='key,summary,description,issuetype,timespent,comment'  # 🔥 ТОЛЬКО НУЖНЫЕ ПОЛЯ + КОММЕНТАРИИ
            )
            
            if not issues:
                print("✅ Больше задач не найдено")
                break
                
            print(f"   📥 Получено {len(issues)} задач")
            
            # Считаем статистику по комментариям для текущей порции
            tasks_with_comments = 0
            total_comments = 0
            
            # Обрабатываем задачи из текущей порции
            for issue in issues:
                comments_text = collect_and_clean_comments(issue)
                
                # Статистика по комментариям
                if comments_text:
                    tasks_with_comments += 1
                    # Считаем количество комментариев по разделителю
                    total_comments += len(comments_text.split(' | '))
                
                all_data.append({
                    'key': issue.key,
                    'title': issue.fields.summary,
                    'description': clean_description(issue.fields.description),
                    'comments': comments_text,  # 🆕 Добавляем комментарии
                    'issuetype': issue.fields.issuetype.name,
                    'time_spent': getattr(issue.fields, 'timespent', 0) or 0,
                    'processing_stage': 'new',  # Этап обработки
                    'category_id': '',          # ID категории (пока пустой)
                    'batch_processed': 0        # Номер батча обработки
                })
            
            # Выводим статистику по комментариям
            if tasks_with_comments > 0:
                print(f"   💬 Задач с комментариями: {tasks_with_comments}, всего комментариев: {total_comments}")
            
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
    
    # Сохраняем задачи в Excel с безопасной обработкой
    main_tasks_file = os.path.join(data_folder, "tasks.xlsx")
    
    print(f"\n💾 Сохраняю задачи в файл...")
    success = safe_save_excel(df, main_tasks_file, 'Tasks')
    
    if success:
        print(f"✅ Задачи успешно сохранены: {main_tasks_file}")
    else:
        print(f"❌ Не удалось сохранить задачи в файл: {main_tasks_file}")
        # Возвращаем None как признак ошибки сохранения
        return df, None
    
    return df, main_tasks_file
