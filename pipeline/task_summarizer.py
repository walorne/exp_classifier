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
    prompt = f"""Ты эксперт по анализу и резюмированию рабочих задач. Проанализируй следующую JIRA задачу и создай резюме по тексту задачи.

Текст задачи:
{task_text}

ПРАВИЛА РЕЗЮМИРОВАНИЯ:
! ВАЖНО: Твое резюме будет использовано для создания классификатора задачи.

1. Обращай внимание на тип задачи.
2. Иногда нас просят просто что-то рассказать, объяснить или проверить. Обычно это задачи консультации. В этом случае обязательно сделай отметку, что это консультация, а не ошибка.
3. Иногда нас просят вывести что-то из эксплуатации. Обычно в задачах упоминают DEP или deprecation. В этом случае обязательно сделай отметку, что это вывод из эксплуатации, а не ошибка.
4. Часто нам указывают, что работа системы не соответсвует ожидаемой, тогда это может быть ошибкой. Чтобы принять решение, нужно тщательно проанализировать текст задачи. Сделать выжимку из текста задачи.
5. Обязательно определи источник проблемы. Обычно это: элемент или компонент системы, внешняя система, просьба, вопрос. Обязательно укажи источник проблемы в резюме.
6. Если в задаче упоминается слой системы, укажи слой в резюме. Слои могут быть уровня: представления - графические интерфейсы, какие-то интерфейсы выглядят не так как ожидалось, поведение элементов интерфейса не соответсвует ожидаемому; Логики - поведение и реакция системы не соответсвует ожидаемому; Данных - в системах хранения данных произошли ошибки, в системе хранения данных некорректные данные; Интеграции - наблюдаются ошибки при взаимодействии систем или компонетов системы посредством интеграций, сбои в интеграциях; Безопасности - ошибки аутентификации и авторизации; Инфраструктуры - проблемы в аппаратном обеспечении, ошибки в инфраструктуре системы, сбои в инфраструктуре системы. Обязательно укажи это в резюме.
7. Уложись в три предложения. Можешь использовать более трех предложений, если три предложения не позволяют выполнить правила резюмирования.
8. В профессиоанльном стиле.
9. Всегда следуй этим правилам.

ФОРМАТ ОТВЕТА:
Текст, построенный по правилам резюмирования, в инфинитивной форме

НЕ ВКЛЮЧАЙ:
- Общие фразы типа "в рамках задачи", "необходимо выполнить"
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
    print(f"\n🤖 Суммаризация {len(tasks_df)} задач (потоков: {max_workers})")
    
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
                  desc="🤖 Обработка задач", 
                  unit="задача",
                  ncols=80,
                  leave=True,
                  dynamic_ncols=False,
                  miniters=0,
                  mininterval=0.5,
                  maxinterval=2.0,
                  smoothing=0.3,
                  position=0,
                  ascii=True,
                  bar_format='{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]') as pbar:
            
            for future in as_completed(future_to_task):
                index, summary, success, error_msg = future.result()
                
                # Сохраняем результат
                result_df.loc[index, 'summary'] = summary
                
                if success:
                    success_count += 1
                else:
                    error_count += 1
                    if "Попытка" in str(error_msg):
                        retry_count += 1
                
                # Обновляем прогресс-бар только с базовой информацией
                pbar.update(1)
    
    # Краткая статистика (после закрытия прогресс-бара)
    print(f"\n✅ Обработано {success_count}/{len(tasks_df)} задач")
    
    # Сохраняем результаты
    
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

def main():
    """
    Основная функция для суммаризации задач
    """
    print("🤖 Суммаризация задач")
    print("=" * 60)

    # ===== НАСТРОЙКИ МНОГОПОТОЧНОСТИ СУММАРИЗАЦИИ=====
    SUMMARIZATION_THREADS = 100  # Количество потоков для суммаризации (рекомендуется 3-5)
    SUMMARIZATION_RETRIES = 3  # Количество повторных попыток при ошибке
    SAVE_TIMESTAMPED_FILES = False
    DATA_FOLDER_PROJECT = "classification_data/MPSM"
    
    # Загружаем задачи из файла
    tasks_file = os.path.join(DATA_FOLDER_PROJECT, "tasks.xlsx")
    if not os.path.exists(tasks_file):
        print(f"❌ Файл с задачами не найден: {tasks_file}")
        print("💡 Поместите файл tasks.xlsx в папку и запустите скрипт снова")
        return
    
    try:
        tasks_df = pd.read_excel(tasks_file)
        print(f"✅ Загружено {len(tasks_df)} задач из файла: {tasks_file}")
        
        # Структура данных загружена
        
    except Exception as e:
        print(f"❌ Ошибка загрузки файла задач: {e}")
        return
    
    # Выполняем генерацию
    try:
        summarized_df, summarized_file = summarize_tasks(
            tasks_df=tasks_df,
            project_folder=DATA_FOLDER_PROJECT,
            save_timestamped=SAVE_TIMESTAMPED_FILES,
            max_workers=SUMMARIZATION_THREADS,
            max_retries=SUMMARIZATION_RETRIES
        )
        
        print(f"\n🎉 ГЕНЕРАЦИЯ ЗАВЕРШЕНА!")
        print(f"   Создано категорий: {len(summarized_df)}")
        print(f"   Файл сохранен: {summarized_file}")
        
    except Exception as e:
        print(f"\n❌ ОШИБКА ПРИ ГЕНЕРАЦИИ: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
