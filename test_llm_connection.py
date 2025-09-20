"""
Тестовый скрипт для проверки подключения к LLM модели
"""
from clients.ai_client import create_default_client
from dotenv import load_dotenv
import os
import time

load_dotenv()

def test_llm_connection():
    """Тестирует подключение к LLM модели"""
    
    print("🤖 Тестирую подключение к LLM модели...")
    print(f"API Base: {os.getenv('LLM_API_BASE')}")
    print(f"Model: {os.getenv('LLM_MODEL')}")
    print(f"API Key: {os.getenv('LLM_API_KEY')[:10]}..." if os.getenv('LLM_API_KEY') else "API Key не найден")
    
    try:
        # Создаем клиент
        llm_client = create_default_client()
        print("✅ LLM клиент создан успешно")
        
        # Простой тестовый запрос
        test_prompt = "Привет! Ответь одним словом: работает ли соединение?"
        
        print("\n📤 Отправляю тестовый запрос...")
        print(f"Запрос: {test_prompt}")
        
        start_time = time.time()
        response = llm_client.simple_chat(test_prompt)
        end_time = time.time()
        
        response_time = end_time - start_time
        
        print(f"✅ Получен ответ за {response_time:.2f} секунд")
        print(f"📥 Ответ: {response[:200]}..." if len(response) > 200 else f"📥 Ответ: {response}")
        
        # Дополнительный тест - более сложный запрос
        print("\n🧪 Тестирую более сложный запрос...")
        complex_prompt = """Проанализируй следующую задачу и создай 1 категорию в формате CSV:

Задача: Исправить ошибку авторизации в мобильном приложении

Формат ответа:
Название;Описание"""
        
        start_time = time.time()
        complex_response = llm_client.simple_chat(complex_prompt)
        end_time = time.time()
        
        complex_response_time = end_time - start_time
        
        print(f"✅ Сложный запрос выполнен за {complex_response_time:.2f} секунд")
        print(f"📥 Ответ: {complex_response[:200]}..." if len(complex_response) > 200 else f"📥 Ответ: {complex_response}")
        
        # Проверяем, что ответ содержит ожидаемый формат
        if ';' in complex_response:
            print("✅ Модель корректно обрабатывает структурированные запросы")
        else:
            print("⚠️ Модель может некорректно обрабатывать структурированные запросы")
        
        print(f"\n🎉 Все тесты пройдены успешно!")
        print(f"⏱️ Среднее время ответа: {(response_time + complex_response_time) / 2:.2f} секунд")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка подключения к LLM: {e}")
        print(f"❌ Тип ошибки: {type(e).__name__}")
        
        # Детальная диагностика ошибок
        error_str = str(e).lower()
        
        print("\n🔧 Возможные решения:")
        
        if 'timeout' in error_str or 'timed out' in error_str:
            print("1. ⏱️ TIMEOUT: Модель недоступна или перегружена")
            print("   - Проверьте доступность сервера LLM")
            print("   - Увеличьте timeout в настройках клиента")
            print("   - Попробуйте позже")
            
        elif 'connection' in error_str:
            print("1. 🌐 CONNECTION: Проблемы с сетевым подключением")
            print("   - Проверьте URL в переменной LLM_API_BASE")
            print("   - Убедитесь, что сервер LLM запущен и доступен")
            print("   - Проверьте сетевые настройки и прокси")
            
        elif 'unauthorized' in error_str or '401' in error_str:
            print("1. 🔐 AUTH: Проблемы с авторизацией")
            print("   - Проверьте правильность API ключа в LLM_API_KEY")
            print("   - Убедитесь, что ключ не истек")
            
        elif 'not found' in error_str or '404' in error_str:
            print("1. 🔍 NOT FOUND: Модель или эндпоинт не найден")
            print("   - Проверьте правильность названия модели в LLM_MODEL")
            print("   - Убедитесь, что API эндпоинт корректен")
            
        else:
            print("1. 🔧 GENERAL: Общая ошибка")
            print("   - Проверьте все переменные окружения в .env файле")
            print("   - Убедитесь, что LLM сервис запущен и работает")
            print("   - Проверьте логи LLM сервера")
        
        print(f"\n📋 Текущие настройки:")
        print(f"   LLM_API_BASE: {os.getenv('LLM_API_BASE', 'НЕ УСТАНОВЛЕНО')}")
        print(f"   LLM_MODEL: {os.getenv('LLM_MODEL', 'НЕ УСТАНОВЛЕНО')}")
        print(f"   LLM_API_KEY: {'УСТАНОВЛЕНО' if os.getenv('LLM_API_KEY') else 'НЕ УСТАНОВЛЕНО'}")
        
        return False

def test_llm_performance():
    """Тестирует производительность LLM модели"""
    print("\n⚡ Тестирую производительность LLM...")
    
    try:
        llm_client = create_default_client()
        
        # Тест скорости на разных размерах запросов
        test_cases = [
            ("Короткий", "Привет"),
            ("Средний", "Проанализируй эту задачу: исправить баг в системе авторизации"),
            ("Длинный", """Проанализируй следующие JIRA задачи и создай категории:
1. Исправить ошибку авторизации в мобильном приложении
2. Добавить новую кнопку на главную страницу
3. Оптимизировать запросы к базе данных
4. Настроить интеграцию с внешним API
5. Исправить отображение графиков в дашборде""")
        ]
        
        for test_name, prompt in test_cases:
            print(f"\n🧪 Тест '{test_name}' ({len(prompt)} символов)...")
            
            start_time = time.time()
            response = llm_client.simple_chat(prompt)
            end_time = time.time()
            
            response_time = end_time - start_time
            chars_per_second = len(response) / response_time if response_time > 0 else 0
            
            print(f"   ⏱️ Время: {response_time:.2f} сек")
            print(f"   📏 Длина ответа: {len(response)} символов")
            print(f"   🚀 Скорость: {chars_per_second:.1f} символов/сек")
            
            if response_time > 30:
                print(f"   ⚠️ Медленный ответ (>{30} сек)")
            elif response_time > 10:
                print(f"   🟡 Умеренная скорость ({response_time:.1f} сек)")
            else:
                print(f"   ✅ Хорошая скорость ({response_time:.1f} сек)")
        
    except Exception as e:
        print(f"❌ Ошибка тестирования производительности: {e}")


if __name__ == "__main__":
    print("="*60)
    print("🤖 ТЕСТИРОВАНИЕ LLM ПОДКЛЮЧЕНИЯ")
    print("="*60)
    
    # Основной тест подключения
    connection_ok = test_llm_connection()
    
    # Тест производительности только если основной тест прошел
    if connection_ok:
        test_llm_performance()
        
        print("\n" + "="*60)
        print("✅ ВСЕ ТЕСТЫ ЗАВЕРШЕНЫ")
        print("="*60)
    else:
        print("\n" + "="*60)
        print("❌ ТЕСТЫ ЗАВЕРШЕНЫ С ОШИБКАМИ")
        print("="*60)
