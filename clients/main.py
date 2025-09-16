"""
Основной файл для работы с моделью Qwen3-Coder
"""
import argparse
import sys
import os
from typing import Optional
# Добавляем родительскую папку в путь для импорта
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from clients.ai_client import LocalGPTClient, create_default_client


def interactive_mode(client: LocalGPTClient):
    """Интерактивный режим общения с моделью"""
    print("🤖 Интерактивный режим с моделью Qwen3-Coder")
    print("Введите 'exit' или 'quit' для выхода")
    print("Введите 'clear' для очистки контекста")
    print("-" * 50)
    
    conversation_history = []
    
    while True:
        try:
            user_input = input("\n👤 Вы: ").strip()
            
            if user_input.lower() in ['exit', 'quit', 'выход']:
                print("До свидания! 👋")
                break
            
            if user_input.lower() in ['clear', 'очистить']:
                conversation_history = []
                print("🗑️ История разговора очищена")
                continue
            
            if not user_input:
                continue
            
            # Добавляем сообщение пользователя в историю
            conversation_history.append({"role": "user", "content": user_input})
            
            print("🤖 Модель думает...")
            
            # Отправляем запрос с полной историей разговора
            response = client.chat_completion(conversation_history)
            
            # Извлекаем ответ
            assistant_message = response["choices"][0]["message"]["content"]
            
            # Добавляем ответ модели в историю
            conversation_history.append({"role": "assistant", "content": assistant_message})
            
            print(f"🤖 Модель: {assistant_message}")
            
        except KeyboardInterrupt:
            print("\n\nПрерывание работы... До свидания! 👋")
            break
        except Exception as e:
            print(f"❌ Ошибка: {e}")


def single_request_mode(client: LocalGPTClient, prompt: str, system_message: Optional[str] = None):
    """Режим одного запроса"""
    try:
        print(f"📝 Отправка запроса: {prompt}")
        response = client.simple_chat(prompt, system_message)
        print(f"🤖 Ответ модели:\n{response}")
    except Exception as e:
        print(f"❌ Ошибка при отправке запроса: {e}")
        sys.exit(1)


def test_connection(client: LocalGPTClient):
    """Тестирование подключения к модели"""
    print("🔍 Проверка подключения к API...")
    
    if not client.health_check():
        print("❌ Не удалось подключиться к API")
        print("Проверьте:")
        print("- Доступность сервера по адресу:", client.api_base)
        print("- Корректность API ключа:", client.api_key[:10] + "...")
        print("- Сетевое подключение")
        sys.exit(1)
    
    print("✅ Подключение к API успешно")
    
    # Получаем информацию о доступных моделях
    try:
        models = client.get_models()
        print(f"📋 Доступно моделей: {len(models.get('data', []))}")
        print(f"🎯 Используемая модель: {client.model}")
    except Exception as e:
        print(f"⚠️ Не удалось получить список моделей: {e}")
    
    # Тестовый запрос
    try:
        print("\n🧪 Отправка тестового запроса...")
        test_response = client.simple_chat("Скажи 'Привет' на русском языке")
        print(f"✅ Тестовый ответ: {test_response}")
    except Exception as e:
        print(f"❌ Ошибка при тестовом запросе: {e}")


def main():
    """Основная функция"""
    parser = argparse.ArgumentParser(
        description="Клиент для работы с моделью Qwen3-Coder",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:
  python main.py                              # Интерактивный режим
  python main.py --test                       # Тест подключения
  python main.py --prompt "Привет, модель!"   # Одиночный запрос
  python main.py --prompt "Напиши код" --system "Ты Python разработчик"
        """
    )
    
    parser.add_argument(
        "--prompt", "-p",
        type=str,
        help="Текст запроса для отправки модели"
    )
    
    parser.add_argument(
        "--system", "-s",
        type=str,
        help="Системное сообщение для настройки поведения модели"
    )
    
    parser.add_argument(
        "--test", "-t",
        action="store_true",
        help="Тестирование подключения к API"
    )
    
    parser.add_argument(
        "--api-base",
        type=str,
        help="Базовый URL API (по умолчанию из конфигурации)"
    )
    
    parser.add_argument(
        "--api-key",
        type=str,
        help="API ключ (по умолчанию из конфигурации)"
    )
    
    parser.add_argument(
        "--model",
        type=str,
        help="Название модели (по умолчанию из конфигурации)"
    )
    
    args = parser.parse_args()
    
    # Создаем клиент
    if args.api_base or args.api_key or args.model:
        # Используем кастомные параметры
        from clients.ai_client import DEFAULT_CONFIG
        config = DEFAULT_CONFIG.copy()
        
        if args.api_base:
            config["api_base"] = args.api_base
        if args.api_key:
            config["api_key"] = args.api_key
        if args.model:
            config["model"] = args.model
            
        client = LocalGPTClient(**config)
    else:
        # Используем конфигурацию по умолчанию
        client = create_default_client()
    
    print("🚀 Клиент для модели Qwen3-Coder запущен")
    print(f"🌐 API: {client.api_base}")
    print(f"🎯 Модель: {client.model}")
    
    # Выбираем режим работы
    if args.test:
        test_connection(client)
    elif args.prompt:
        single_request_mode(client, args.prompt, args.system)
    else:
        # Сначала тестируем подключение
        test_connection(client)
        print("\n" + "="*50)
        # Затем запускаем интерактивный режим
        interactive_mode(client)


if __name__ == "__main__":
    main()
