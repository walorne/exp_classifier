"""
Модуль для суммаризации задач по одной с помощью LLM
Обрабатывает задачи индивидуально для получения сути выполняемых работ
"""
import pandas as pd
import os
import time
from datetime import datetime
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed
from clients.ai_client import create_default_client
from utils.file_utils import safe_save_excel


def summarize_single_task_with_retries(task_data, max_retries=3):
    """
    Суммаризирует одну задачу с повторными попытками при ошибках
    
    Args:
        task_data: tuple (index, task_row) - индекс и данные задачи
        max_retries: максимальное количество попыток
    
    Returns:
        tuple: (index, summary, success, error_msg)
    """
    index, task_row = task_data
    task_key = task_row.get('key', f'Task_{index}')
    
    # Создаем отдельный клиент для каждого потока
    llm_client = create_default_client()
    
    for attempt in range(max_retries):
        try:
            summary = summarize_single_task(task_row, llm_client)
            return index, summary, True, None
            
        except Exception as e:
            error_msg = f"Попытка {attempt + 1}/{max_retries}: {str(e)}"
            if attempt == max_retries - 1:  # Последняя попытка
                return index, f"Ошибка после {max_retries} попыток: {str(e)}", False, error_msg
            
            # Небольшая задержка между попытками
            time.sleep(0.5 * (attempt + 1))
    
    return index, "Ошибка суммаризации", False, "Превышено количество попыток"


def summarize_single_task(task_row, llm_client):
    """
    Суммаризирует одну задачу, извлекая суть выполняемых работ
    
    Args:
        task_row: строка DataFrame с данными задачи
        llm_client: клиент для работы с LLM
    
    Returns:
        str: суммаризированное описание задачи
    """
    # Формируем полный текст задачи
    task_text = f"""Тип: {task_row.get('issuetype', 'Не указан')}
Название: {task_row.get('title', 'Не указано')}
Описание: {task_row.get('description', 'Не указано')}
Комментарии: {task_row.get('comments', 'Нет комментариев')}"""

    # Создаем промпт для суммаризации
    prompt = f"""Ты эксперт по анализу рабочих задач. Проанализируй следующую JIRA задачу и создай краткую суммаризацию.

ЗАДАЧА ДЛЯ АНАЛИЗА:
{task_text}

ТРЕБОВАНИЯ К СУММАРИЗАЦИИ:
1. Оставь только СУТЬ - какие работы нужно выполнить по задаче
2. Укажи ГДЕ должны выполняться работы (система, модуль, компонент)
3. Убери лишние детали, технические подробности и общие фразы
4. Фокусируйся на ДЕЙСТВИЯХ которые нужно выполнить
5. Максимум 2-3 предложения
6. Используй деловой стиль без эмоциональной окраски
7. ВАЖНО: описывай работы в стиле "что нужно сделать", а НЕ "что уже сделано"

ФОРМАТ ОТВЕТА:
Краткое описание работ и место их выполнения в инфинитивной форме

ПРИМЕР ПРАВИЛЬНОЙ СУММАРИЗАЦИИ:
"Настроить интеграцию с внешним API платежной системы в модуле billing. Исправить ошибку обработки timeout при запросах к сервису авторизации."

НЕПРАВИЛЬНО (прошедшее время):
"Настроена интеграция с внешним API платежной системы. Исправлена ошибка обработки timeout."

ПРАВИЛЬНО (инфинитив):
"Настроить интеграцию с внешним API платежной системы. Исправить ошибку обработки timeout."

НЕ ВКЛЮЧАЙ:
- Общие фразы типа "в рамках задачи", "необходимо выполнить"
- Технические детали реализации
- Планы на будущее
- Благодарности и эмоции

ВЕРНИ ТОЛЬКО СУММАРИЗАЦИЮ БЕЗ ДОПОЛНИТЕЛЬНОГО ТЕКСТА."""

    try:
        response = llm_client.simple_chat(prompt)
        return response.strip()
    except Exception as e:
        print(f"❌ Ошибка суммаризации задачи {task_row.get('key', 'Unknown')}: {e}")
        return f"Ошибка суммаризации: {str(e)}"


def process_tasks_individually(tasks_df, project_folder, save_timestamped=True, max_workers=3, max_retries=3):
    """
    Обрабатывает задачи по одной для суммаризации с многопоточностью
    
    Args:
        tasks_df (pd.DataFrame): DataFrame с задачами
        project_folder (str): полный путь к папке проекта для сохранения файлов
        save_timestamped (bool): сохранять ли файлы с временными метками
        max_workers (int): количество потоков для обработки
        max_retries (int): количество повторных попыток при ошибке
    
    Returns:
        pd.DataFrame: DataFrame с суммаризированными задачами
        str: путь к файлу с результатами
    """
    print(f"\n🤖 Суммаризация {len(tasks_df)} задач с многопоточностью...")
    print(f"📂 Папка проекта: {project_folder}")
    print(f"🧵 Потоков: {max_workers}, повторов при ошибке: {max_retries}")
    
    # Создаем папку для проекта
    os.makedirs(project_folder, exist_ok=True)
    
    # Копируем исходный DataFrame и добавляем колонку для суммаризации
    result_df = tasks_df.copy()
    result_df['summary'] = ""
    
    # Счетчики для статистики
    success_count = 0
    error_count = 0
    retry_count = 0
    
    # Подготавливаем данные для обработки (index, row)
    task_data = [(index, row) for index, row in tasks_df.iterrows()]
    
    # Многопоточная обработка с прогресс-баром
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Отправляем все задачи в пул потоков
        future_to_task = {
            executor.submit(summarize_single_task_with_retries, data, max_retries): data[0] 
            for data in task_data
        }
        
        # Обрабатываем результаты по мере готовности
        with tqdm(total=len(tasks_df), 
                  desc="🤖 Суммаризация задач", 
                  unit="задача",
                  bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]') as pbar:
            
            for future in as_completed(future_to_task):
                index, summary, success, error_msg = future.result()
                task_key = tasks_df.loc[index, 'key'] if 'key' in tasks_df.columns else f'Task_{index}'
                
                # Сохраняем результат
                result_df.loc[index, 'summary'] = summary
                
                if success:
                    success_count += 1
                    status = '✅'
                else:
                    error_count += 1
                    status = '❌'
                    if "Попытка" in str(error_msg):
                        retry_count += 1
                
                # Обновляем прогресс-бар
                pbar.set_description(f"🤖 {task_key}")
                pbar.set_postfix({
                    'Успешно': success_count,
                    'Ошибок': error_count,
                    'Повторов': retry_count,
                    'Статус': status
                })
                pbar.update(1)
    
    # Итоговая статистика
    print(f"\n📊 Статистика суммаризации:")
    print(f"   ✅ Успешно обработано: {success_count}")
    print(f"   ❌ Ошибок: {error_count}")
    print(f"   📈 Процент успеха: {(success_count/len(tasks_df)*100):.1f}%")
    
    # Сохраняем результаты
    print(f"\n📋 Суммаризация завершена! Сохраняю результаты...")
    
    success1 = True
    summary_file = None
    
    # Сохраняем файл с временной меткой только если включено
    if save_timestamped:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        summary_file = os.path.join(project_folder, f"tasks_summary_{timestamp}.xlsx")
        success1 = safe_save_excel(result_df, summary_file, 'Summarized_Tasks')
    
    # Всегда сохраняем основной файл
    main_summary_file = os.path.join(project_folder, "tasks_summary.xlsx")
    success2 = safe_save_excel(result_df, main_summary_file, 'Summarized_Tasks')
    
    # Выводим результаты сохранения
    if save_timestamped:
        if success1 and success2:
            print(f"\n✅ Все файлы успешно сохранены:")
            print(f"   📄 Файл с результатами: {summary_file}")
            print(f"   📄 Основной файл: {main_summary_file}")
        elif success1 or success2:
            print(f"\n⚠️ Частично сохранено:")
            if success1:
                print(f"   ✅ Файл с результатами: {summary_file}")
            if success2:
                print(f"   ✅ Основной файл: {main_summary_file}")
        else:
            print(f"\n❌ Не удалось сохранить файлы!")
    else:
        if success2:
            print(f"\n✅ Файл успешно сохранен: {main_summary_file}")
        else:
            print(f"\n❌ Не удалось сохранить файл: {main_summary_file}")
    
    return result_df, summary_file if (save_timestamped and success1) else main_summary_file if success2 else None


def summarize_tasks(tasks_df, project_folder, save_timestamped=True, max_workers=3, max_retries=3):
    """
    Основная функция для суммаризации задач
    
    Args:
        tasks_df (pd.DataFrame): DataFrame с задачами
        project_folder (str): полный путь к папке проекта для сохранения файлов
        save_timestamped (bool): сохранять ли файлы с временными метками
        max_workers (int): количество потоков для обработки
        max_retries (int): количество повторных попыток при ошибке
    
    Returns:
        pd.DataFrame: DataFrame с суммаризированными задачами
        str: путь к файлу с результатами
    """
    return process_tasks_individually(tasks_df, project_folder, save_timestamped, max_workers, max_retries)


if __name__ == "__main__":
    # Пример использования
    print("📝 Модуль суммаризации задач")
    print("Используйте функцию summarize_tasks() для обработки задач")
