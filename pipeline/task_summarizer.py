"""
Модуль для суммаризации задач по одной с помощью LLM
Обрабатывает задачи индивидуально для получения сути выполняемых работ
"""
import pandas as pd
import os
from datetime import datetime
from tqdm import tqdm
from clients.ai_client import create_default_client
from utils.file_utils import safe_save_excel


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


def process_tasks_individually(tasks_df, project_folder, save_timestamped=True):
    """
    Обрабатывает задачи по одной для суммаризации
    
    Args:
        tasks_df (pd.DataFrame): DataFrame с задачами
        project_folder (str): полный путь к папке проекта для сохранения файлов
        save_timestamped (bool): сохранять ли файлы с временными метками
    
    Returns:
        pd.DataFrame: DataFrame с суммаризированными задачами
        str: путь к файлу с результатами
    """
    print(f"\n🤖 Суммаризация {len(tasks_df)} задач по одной...")
    print(f"📂 Папка проекта: {project_folder}")
    
    # Создаем LLM клиент
    llm_client = create_default_client()
    
    # Создаем папку для проекта
    os.makedirs(project_folder, exist_ok=True)
    
    # Копируем исходный DataFrame и добавляем колонку для суммаризации
    result_df = tasks_df.copy()
    result_df['summary'] = ""
    
    # Счетчики для статистики
    success_count = 0
    error_count = 0
    
    # Обрабатываем каждую задачу с прогресс-баром
    with tqdm(total=len(tasks_df), 
              desc="🤖 Суммаризация задач", 
              unit="задача",
              bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]') as pbar:
        
        for index, row in tasks_df.iterrows():
            task_key = row.get('key', f'Task_{index}')
            pbar.set_description(f"🤖 {task_key}")
            
            try:
                summary = summarize_single_task(row, llm_client)
                result_df.loc[index, 'summary'] = summary
                success_count += 1
                pbar.set_postfix({
                    'Успешно': success_count,
                    'Ошибок': error_count,
                    'Статус': '✅'
                })
                
            except Exception as e:
                error_msg = f"Ошибка обработки: {str(e)}"
                result_df.loc[index, 'summary'] = error_msg
                error_count += 1
                pbar.set_postfix({
                    'Успешно': success_count,
                    'Ошибок': error_count,
                    'Статус': '❌'
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


def summarize_tasks(tasks_df, project_folder, save_timestamped=True):
    """
    Основная функция для суммаризации задач
    
    Args:
        tasks_df (pd.DataFrame): DataFrame с задачами
        project_folder (str): полный путь к папке проекта для сохранения файлов
        save_timestamped (bool): сохранять ли файлы с временными метками
    
    Returns:
        pd.DataFrame: DataFrame с суммаризированными задачами
        str: путь к файлу с результатами
    """
    return process_tasks_individually(tasks_df, project_folder, save_timestamped)


if __name__ == "__main__":
    # Пример использования
    print("📝 Модуль суммаризации задач")
    print("Используйте функцию summarize_tasks() для обработки задач")
