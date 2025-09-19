"""
Утилиты для безопасной работы с файлами
"""
import os
import pandas as pd
from time import sleep


def safe_save_excel(df, file_path, sheet_name='Sheet1', max_retries=5, show_success_message=True):
    """
    Безопасное сохранение DataFrame в Excel файл с обработкой ошибок доступа
    
    Args:
        df (pd.DataFrame): DataFrame для сохранения
        file_path (str): путь к файлу
        sheet_name (str): название листа
        max_retries (int): максимальное количество попыток
        show_success_message (bool): показывать ли сообщение об успешном сохранении
    
    Returns:
        bool: True если файл сохранен успешно, False если не удалось
    """
    attempt = 1
    
    while attempt <= max_retries:
        try:
            # Создаем папку если её нет
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            # Пробуем сохранить файл
            df.to_excel(file_path, index=False, sheet_name=sheet_name)
            if show_success_message:
                print(f"✅ Файл успешно сохранен: {file_path}")
            return True
            
        except PermissionError:
            print(f"\n⚠️ ОШИБКА ДОСТУПА К ФАЙЛУ (попытка {attempt}/{max_retries})")
            print(f"📁 Файл: {file_path}")
            print(f"🔒 Файл заблокирован - вероятно открыт в Excel или другом приложении")
            print(f"💡 Закройте файл и нажмите Enter для продолжения...")
            
            # Ждем подтверждения пользователя
            try:
                input("   Нажмите Enter когда файл будет закрыт: ")
            except KeyboardInterrupt:
                print("\n❌ Сохранение отменено пользователем")
                return False
            
            attempt += 1
            
        except Exception as e:
            print(f"❌ Неожиданная ошибка при сохранении файла: {e}")
            print(f"📁 Файл: {file_path}")
            return False
    
    print(f"❌ Не удалось сохранить файл после {max_retries} попыток: {file_path}")
    return False


def safe_save_multiple_sheets(data_dict, file_path, max_retries=5):
    """
    Безопасное сохранение нескольких DataFrame в один Excel файл с разными листами
    
    Args:
        data_dict (dict): словарь {sheet_name: dataframe}
        file_path (str): путь к файлу
        max_retries (int): максимальное количество попыток
    
    Returns:
        bool: True если файл сохранен успешно, False если не удалось
    """
    attempt = 1
    
    while attempt <= max_retries:
        try:
            # Создаем папку если её нет
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            # Пробуем сохранить файл с несколькими листами
            with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
                for sheet_name, df in data_dict.items():
                    df.to_excel(writer, sheet_name=sheet_name, index=False)
            
            print(f"✅ Файл с {len(data_dict)} листами успешно сохранен: {file_path}")
            return True
            
        except PermissionError:
            print(f"\n⚠️ ОШИБКА ДОСТУПА К ФАЙЛУ (попытка {attempt}/{max_retries})")
            print(f"📁 Файл: {file_path}")
            print(f"🔒 Файл заблокирован - вероятно открыт в Excel или другом приложении")
            print(f"💡 Закройте файл и нажмите Enter для продолжения...")
            
            # Ждем подтверждения пользователя
            try:
                input("   Нажмите Enter когда файл будет закрыт: ")
            except KeyboardInterrupt:
                print("\n❌ Сохранение отменено пользователем")
                return False
            
            attempt += 1
            
        except Exception as e:
            print(f"❌ Неожиданная ошибка при сохранении файла: {e}")
            print(f"📁 Файл: {file_path}")
            return False
    
    print(f"❌ Не удалось сохранить файл после {max_retries} попыток: {file_path}")
    return False


def check_file_access(file_path):
    """
    Проверяет доступность файла для записи
    
    Args:
        file_path (str): путь к файлу
    
    Returns:
        bool: True если файл доступен для записи
    """
    try:
        # Если файл не существует, проверяем доступность папки
        if not os.path.exists(file_path):
            dir_path = os.path.dirname(file_path)
            if dir_path and not os.path.exists(dir_path):
                os.makedirs(dir_path, exist_ok=True)
            return True
        
        # Если файл существует, пробуем открыть его для записи
        with open(file_path, 'a'):
            pass
        return True
        
    except PermissionError:
        return False
    except Exception:
        return False
