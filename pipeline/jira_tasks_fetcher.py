"""
Модуль для получения задач из JIRA и сохранения в Excel
"""
import pandas as pd
import os
import re
from datetime import datetime
from tqdm import tqdm
from clients.jira_client import get_jira_client, get_field_value, safe_get_custom_field
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


def fetch_and_save_tasks(jql_query, data_folder="classification_data", chunk_size=100, max_results=None, save_timestamped=True):
    """
    Получает задачи из JIRA по JQL запросу частями и сохраняет в Excel
    
    ОПТИМИЗАЦИИ:
    - Загрузка порциями (chunk_size) вместо всех задач сразу
    - Запрос только нужных полей: key, summary, description, issuetype, timespent
    - Быстрый подсчет общего количества с минимальными полями
    
    Args:
        jql_query (str): JQL запрос для получения задач
        data_folder (str): папка для сохранения файлов
        chunk_size (int): размер порции для загрузки (рекомендуется 25-100)
        max_results (int): максимальное количество задач (None = все)
        save_timestamped (bool): сохранять ли файлы с временными метками
    
    Returns:
        pd.DataFrame: DataFrame с задачами
        str: путь к основному файлу задач
    """
    print(f"🔍 Выполняю JQL запрос частями по {chunk_size} задач...")
    
    # Подключаемся к JIRA
    jira = get_jira_client()
    
    # Сначала узнаем общее количество задач (быстрый запрос без полей)
    try:
        print("🔍 Выполняю предварительный подсчет задач...")
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
            print("   - Проверьте права доступа к проекту и эпику")
        elif "issueFunction" in str(e).lower():
            print("🔌 Проблема с функцией issuesInEpics:")
            print("   - Убедитесь что ScriptRunner или аналогичный плагин установлен")
            print("   - Проверьте синтаксис JQL запроса")
        elif "timeout" in str(e).lower():
            print("⏰ Таймаут запроса:")
            print("   - JQL запрос слишком сложный, увеличен таймаут до 60 сек")
        print("Продолжаем загрузку порциями...")
        total_count = None
    
    # Подготавливаем прогресс-бар
    if total_count:
        total_to_fetch = min(total_count, max_results) if max_results else total_count
        print(f"📥 Загружаю {total_to_fetch} задач порциями по {chunk_size}")
    else:
        total_to_fetch = max_results if max_results else None
        if total_to_fetch:
            print(f"📥 Загружаю до {total_to_fetch} задач порциями по {chunk_size}")
        else:
            print(f"📥 Загружаю задачи порциями по {chunk_size}")
    
    # Загружаем задачи порциями с прогресс-баром
    all_data = []
    start_at = 0
    
    # Создаем прогресс-бар с принудительным обновлением на месте
    if total_to_fetch:
        pbar = tqdm(total=total_to_fetch, 
                   desc="📥 Загрузка задач", 
                   unit="задача",
                   ncols=80,
                   leave=True,  # Оставляем бар после завершения
                   dynamic_ncols=False,
                   miniters=0,  # Обновлять всегда
                   mininterval=0.5,  # Реже обновления - меньше мерцания
                   maxinterval=2.0,  # Максимум раз в 2 секунды
                   smoothing=0.3,    # Больше сглаживания
                   position=0,       # Позиция на экране
                   ascii=True,       # ASCII символы вместо Unicode
                   bar_format='{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]')
    else:
        pbar = None
    
    try:
        while True:
            # Ограничиваем размер порции если приближаемся к лимиту
            current_chunk_size = chunk_size
            if max_results and start_at + chunk_size > max_results:
                current_chunk_size = max_results - start_at
                
            if current_chunk_size <= 0:
                break
                
            try:
                # Загружаем порцию только с нужными полями (для скорости)
                issues = jira.search_issues(
                    jql_query, 
                    startAt=start_at, 
                    maxResults=current_chunk_size,
                    fields='key,summary,description,issuetype,timespent,comment,customfield_19003,customfield_12407,customfield_20703'  # 🔥 ТОЛЬКО НУЖНЫЕ ПОЛЯ + КОММЕНТАРИИ
                )
                
                if not issues:
                    break
                    
                # Считаем статистику по комментариям для текущей порции
                tasks_with_comments = 0
                total_comments = 0
            
                # Обрабатываем задачи из текущей порции
                for issue in issues:
                    comments_text = collect_and_clean_comments(issue)
                    cf_19003 = get_field_value(safe_get_custom_field(issue.fields, 'customfield_19003'))
                    cf_12407 = get_field_value(safe_get_custom_field(issue.fields, 'customfield_12407'))
                    cf_20703 = get_field_value(safe_get_custom_field(issue.fields, 'customfield_20703'))                    
                    # Статистика по комментариям
                    if comments_text:
                        tasks_with_comments += 1
                        # Считаем количество комментариев по разделителю
                        total_comments += len(comments_text.split(' | '))
                    
                    all_data.append({
                        'key': issue.key,
                        'Team': cf_19003,
                        'type': cf_12407,
                        'stage': cf_20703,
                        'title': issue.fields.summary,
                        'description': clean_description(issue.fields.description),
                        'comments': comments_text,  # 🆕 Добавляем комментарии
                        'issuetype': issue.fields.issuetype.name,
                        # Переводим время из секунд в часы, округляем до сотых
                        'time_spent_hours': round((getattr(issue.fields, 'timespent', 0) or 0) / 3600, 2),
                        'processing_stage': 'new',  # Этап обработки
                        'category_id': '',          # ID категории (пока пустой)
                        'batch_processed': 0        # Номер батча обработки
                    })
                
                # Обновляем прогресс-бар
                if pbar:
                    pbar.update(len(issues))
                
                # Переходим к следующей порции
                start_at += len(issues)
                
                # Если получили меньше задач чем запрашивали - это последняя порция
                if len(issues) < current_chunk_size:
                    break
                    
                # Если достигли лимита
                if max_results and start_at >= max_results:
                    break
                    
            except Exception as e:
                if pbar:
                    pbar.close()
                print(f"❌ Ошибка при загрузке: {e}")
                if "401" in str(e):
                    print("💡 Проблема с аутентификацией - проверьте токен!")
                    raise
                break
    
    finally:
        # Принудительно завершаем прогресс-бар
        if pbar:
            pbar.close()
            print()  # Добавляем пустую строку для отделения

    if not all_data:
        print("❌ Не удалось загрузить ни одной задачи!")
        raise Exception("Нет данных для обработки")

    df = pd.DataFrame(all_data)
    
    # Краткая статистика по комментариям
    tasks_with_comments = df['comments'].apply(lambda x: len(x.strip()) > 0).sum()
    if tasks_with_comments > 0:
        print(f"\n✅ Загружено {len(df)} задач, с комментариями: {tasks_with_comments}")
    else:
        print(f"\n✅ Загружено {len(df)} задач")
    
    # Сохраняем задачи в Excel с безопасной обработкой
    success1 = True
    tasks_file = None
    
    if save_timestamped:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        tasks_file = os.path.join(data_folder, f"tasks_{timestamp}.xlsx")
        success1 = safe_save_excel(df, tasks_file, 'Tasks', show_success_message=False)
    
    # Основной файл задач
    main_tasks_file = os.path.join(data_folder, "tasks.xlsx")
    success2 = safe_save_excel(df, main_tasks_file, 'Tasks', show_success_message=False)
    
    if save_timestamped and success1 and success2:
        return df, tasks_file
    elif success2:
        return df, main_tasks_file
    else:
        print(f"❌ Не удалось сохранить задачи")
        return df, None
