"""
Демонстрация работы с утилитами LocalGPT
"""
import argparse
import sys
import os
# Добавляем родительскую папку в путь
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from clients.client import create_default_client
from .utils import ModelManager, ConversationLogger, ModelBenchmark, interactive_model_selector


def demo_models(client):
    """Демо работы с моделями"""
    print("🎯 === ДЕМО: Работа с моделями ===")
    
    manager = ModelManager(client)
    
    # Показать доступные модели
    manager.print_models_info()
    
    # Интерактивный выбор модели
    print("\n🔄 Интерактивный выбор модели:")
    selected_model = interactive_model_selector(client)
    
    if selected_model and selected_model != client.model:
        # Переключиться на выбранную модель
        if manager.switch_model(selected_model):
            print(f"✅ Теперь используется модель: {client.model}")
        else:
            print("❌ Не удалось переключиться на выбранную модель")


def demo_logger(client):
    """Демо логгера разговоров"""
    print("\n📝 === ДЕМО: Логгер разговоров ===")
    
    logger = ConversationLogger()
    
    # Начать сессию
    session_id = logger.start_session("demo_session")
    print(f"🎬 Начата сессия: {session_id}")
    
    # Симуляция разговора
    conversation = [
        ("user", "Привет! Как дела?"),
        ("assistant", "Привет! Всё отлично, готов помочь!"),
        ("user", "Расскажи анекдот"),
        ("assistant", "Программист приходит домой и говорит жене: 'Дорогая, я исправил баг!' Жена: 'Какой?' Программист: 'Теперь программа падает намного быстрее!'")
    ]
    
    for role, content in conversation:
        logger.log_message(role, content, client.model, client.api_base)
        print(f"📨 {role}: {content[:50]}...")
    
    # Сохранить сессию
    log_file = logger.save_session()
    print(f"💾 Разговор сохранен в: {log_file}")
    
    # Показать список сессий
    sessions = logger.list_sessions()
    print(f"📚 Всего сохранено сессий: {len(sessions)}")
    
    return log_file


def demo_benchmark(client):
    """Демо бенчмарка производительности"""
    print("\n⚡ === ДЕМО: Бенчмарк производительности ===")
    
    benchmark = ModelBenchmark(client)
    
    # Быстрый тест
    test_prompts = [
        "Привет!",
        "Что такое Python?",
        "Напиши функцию hello_world()"
    ]
    
    print("🧪 Запуск бенчмарка...")
    results = benchmark.run_benchmark(test_prompts)
    
    # Показать результаты
    print("\n📊 РЕЗУЛЬТАТЫ БЕНЧМАРКА:")
    print(f"🎯 Модель: {results['model']}")
    print(f"🌐 API: {results['api_base']}")
    print(f"⏰ Время тестирования: {results['timestamp']}")
    print("-" * 60)
    
    total_avg = 0
    for i, test in enumerate(results['tests'], 1):
        print(f"{i}. Запрос: {test['prompt'][:30]}...")
        print(f"   ⏱️  Среднее время: {test['avg_time']:.2f}s")
        print(f"   📈 Медиана: {test['median_time']:.2f}s")
        print(f"   ✅ Успешность: {test['success_rate']*100:.0f}%")
        print()
        total_avg += test['avg_time']
    
    print(f"🎯 ОБЩЕЕ СРЕДНЕЕ ВРЕМЯ: {total_avg/len(results['tests']):.2f}s")
    
    return results


def demo_all(client):
    """Полная демонстрация всех утилит"""
    print("🚀 === ПОЛНАЯ ДЕМОНСТРАЦИЯ УТИЛИТ ===")
    
    # 1. Модели
    demo_models(client)
    
    # 2. Логгер
    log_file = demo_logger(client)
    
    # 3. Бенчмарк
    results = demo_benchmark(client)
    
    print("\n🎉 === ДЕМОНСТРАЦИЯ ЗАВЕРШЕНА ===")
    print(f"📁 Лог сохранен: {log_file}")
    print(f"⚡ Средняя скорость: {sum(t['avg_time'] for t in results['tests'])/len(results['tests']):.2f}s")
    print("✨ Все утилиты работают корректно!")


def main():
    """Главная функция"""
    parser = argparse.ArgumentParser(
        description="Демонстрация утилит LocalGPT",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:
  python demo_utils.py                    # Полная демонстрация
  python demo_utils.py --models           # Только работа с моделями
  python demo_utils.py --logger           # Только логгер
  python demo_utils.py --benchmark        # Только бенчмарк
        """
    )
    
    parser.add_argument(
        "--models", "-m",
        action="store_true",
        help="Демонстрация работы с моделями"
    )
    
    parser.add_argument(
        "--logger", "-l",
        action="store_true",
        help="Демонстрация логгера разговоров"
    )
    
    parser.add_argument(
        "--benchmark", "-b",
        action="store_true",
        help="Демонстрация бенчмарка производительности"
    )
    
    args = parser.parse_args()
    
    # Создаем клиент
    print("🔌 Подключение к LocalGPT...")
    client = create_default_client()
    
    # Проверяем подключение
    if not client.health_check():
        print("❌ Не удалось подключиться к API")
        return
    
    print("✅ Подключение успешно!")
    print(f"🎯 Модель: {client.model}")
    print(f"🌐 API: {client.api_base}")
    
    # Выбираем режим демонстрации
    if args.models:
        demo_models(client)
    elif args.logger:
        demo_logger(client)
    elif args.benchmark:
        demo_benchmark(client)
    else:
        demo_all(client)


if __name__ == "__main__":
    main()
