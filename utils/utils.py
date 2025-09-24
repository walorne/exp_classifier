"""
Утилиты для работы с моделями LocalGPT
"""
import json
import time
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
import sys
import os

# Добавляем родительскую папку в путь для импорта clients
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from clients.client import LocalGPTClient, create_default_client


class ModelManager:
    """Менеджер для работы с несколькими моделями"""
    
    def __init__(self, client: LocalGPTClient):
        self.client = client
        self._models_cache = None
        self._models_cache_time = None
        self.cache_duration = 300  # 5 минут
    
    def get_available_models(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """
        Получить список доступных моделей с кешированием
        
        Args:
            force_refresh: Принудительно обновить кеш
            
        Returns:
            Список доступных моделей
        """
        current_time = time.time()
        
        # Проверяем кеш
        if (not force_refresh and 
            self._models_cache is not None and 
            self._models_cache_time is not None and 
            current_time - self._models_cache_time < self.cache_duration):
            return self._models_cache
        
        # Обновляем кеш
        try:
            models_response = self.client.get_models()
            self._models_cache = models_response.get('data', [])
            self._models_cache_time = current_time
            return self._models_cache
        except Exception as e:
            print(f"❌ Ошибка при получении списка моделей: {e}")
            return []
    
    def print_models_info(self):
        """Вывести информацию о доступных моделях"""
        models = self.get_available_models()
        
        if not models:
            print("❌ Модели не найдены")
            return
        
        print(f"📋 Доступно моделей: {len(models)}")
        print("-" * 80)
        
        for i, model in enumerate(models, 1):
            model_id = model.get('id', 'N/A')
            created = model.get('created', 0)
            owned_by = model.get('owned_by', 'N/A')
            
            # Форматируем время создания
            if created:
                created_time = datetime.fromtimestamp(created).strftime('%Y-%m-%d %H:%M:%S')
            else:
                created_time = 'N/A'
            
            print(f"{i:2d}. 🎯 ID: {model_id}")
            print(f"    📅 Создана: {created_time}")
            print(f"    👤 Владелец: {owned_by}")
            
            # Дополнительная информация если есть
            if 'object' in model:
                print(f"    🔧 Тип: {model['object']}")
            
            print()
    
    def switch_model(self, model_id: str) -> bool:
        """
        Переключиться на другую модель
        
        Args:
            model_id: ID модели для переключения
            
        Returns:
            True если переключение успешно, False иначе
        """
        models = self.get_available_models()
        available_ids = [model.get('id') for model in models]
        
        if model_id not in available_ids:
            print(f"❌ Модель '{model_id}' не найдена в списке доступных")
            print(f"Доступные модели: {', '.join(available_ids)}")
            return False
        
        old_model = self.client.model
        self.client.model = model_id
        
        # Тестируем новую модель
        try:
            test_response = self.client.simple_chat("test")
            print(f"✅ Успешно переключились с '{old_model}' на '{model_id}'")
            return True
        except Exception as e:
            # Откатываемся назад
            self.client.model = old_model
            print(f"❌ Ошибка при переключении на модель '{model_id}': {e}")
            return False


class ConversationLogger:
    """Логгер для сохранения разговоров"""
    
    def __init__(self, log_dir: str = "logs"):
        self.log_dir = log_dir
        self.current_session = None
        self.session_start_time = None
        
        # Создаем папку для логов если её нет
        os.makedirs(log_dir, exist_ok=True)
    
    def start_session(self, session_name: Optional[str] = None) -> str:
        """
        Начать новую сессию логирования
        
        Args:
            session_name: Имя сессии (опционально)
            
        Returns:
            ID сессии
        """
        self.session_start_time = datetime.now()
        
        if session_name:
            session_id = f"{session_name}_{self.session_start_time.strftime('%Y%m%d_%H%M%S')}"
        else:
            session_id = f"session_{self.session_start_time.strftime('%Y%m%d_%H%M%S')}"
        
        self.current_session = {
            "session_id": session_id,
            "start_time": self.session_start_time.isoformat(),
            "messages": [],
            "metadata": {
                "model": None,
                "api_base": None
            }
        }
        
        return session_id
    
    def log_message(self, role: str, content: str, model: Optional[str] = None, 
                   api_base: Optional[str] = None, metadata: Optional[Dict] = None):
        """
        Записать сообщение в лог
        
        Args:
            role: Роль отправителя (user/assistant/system)
            content: Содержимое сообщения
            model: Используемая модель
            api_base: API endpoint
            metadata: Дополнительные метаданные
        """
        if not self.current_session:
            self.start_session()
        
        message = {
            "timestamp": datetime.now().isoformat(),
            "role": role,
            "content": content
        }
        
        if metadata:
            message["metadata"] = metadata
        
        self.current_session["messages"].append(message)
        
        # Обновляем метаданные сессии
        if model:
            self.current_session["metadata"]["model"] = model
        if api_base:
            self.current_session["metadata"]["api_base"] = api_base
    
    def save_session(self, filename: Optional[str] = None) -> str:
        """
        Сохранить текущую сессию в файл
        
        Args:
            filename: Имя файла (опционально)
            
        Returns:
            Путь к сохраненному файлу
        """
        if not self.current_session:
            raise ValueError("Нет активной сессии для сохранения")
        
        if not filename:
            filename = f"{self.current_session['session_id']}.json"
        
        filepath = os.path.join(self.log_dir, filename)
        
        # Добавляем время окончания сессии
        self.current_session["end_time"] = datetime.now().isoformat()
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.current_session, f, ensure_ascii=False, indent=2)
        
        return filepath
    
    def load_session(self, filepath: str) -> Dict[str, Any]:
        """
        Загрузить сессию из файла
        
        Args:
            filepath: Путь к файлу сессии
            
        Returns:
            Данные сессии
        """
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def list_sessions(self) -> List[str]:
        """Получить список сохраненных сессий"""
        if not os.path.exists(self.log_dir):
            return []
        
        sessions = []
        for filename in os.listdir(self.log_dir):
            if filename.endswith('.json'):
                sessions.append(os.path.join(self.log_dir, filename))
        
        return sorted(sessions, key=os.path.getmtime, reverse=True)


class ModelBenchmark:
    """Бенчмарк для тестирования производительности моделей"""
    
    def __init__(self, client: LocalGPTClient):
        self.client = client
    
    def measure_response_time(self, prompt: str, iterations: int = 3) -> Tuple[float, float, List[float]]:
        """
        Измерить время ответа модели
        
        Args:
            prompt: Тестовый запрос
            iterations: Количество итераций
            
        Returns:
            Кортеж (среднее_время, медиана, список_времен)
        """
        times = []
        
        for i in range(iterations):
            start_time = time.time()
            try:
                self.client.simple_chat(prompt)
                end_time = time.time()
                response_time = end_time - start_time
                times.append(response_time)
                print(f"Итерация {i+1}: {response_time:.2f}s")
            except Exception as e:
                print(f"Ошибка в итерации {i+1}: {e}")
        
        if not times:
            return 0.0, 0.0, []
        
        avg_time = sum(times) / len(times)
        sorted_times = sorted(times)
        median_time = sorted_times[len(sorted_times) // 2]
        
        return avg_time, median_time, times
    
    def run_benchmark(self, test_prompts: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Запустить полный бенчмарк
        
        Args:
            test_prompts: Список тестовых запросов
            
        Returns:
            Результаты бенчмарка
        """
        if not test_prompts:
            test_prompts = [
                "Привет!",
                "Объясни, что такое машинное обучение в одном предложении.",
                "Напиши простую функцию сортировки на Python.",
                "Переведи 'Hello, world!' на русский язык."
            ]
        
        results = {
            "model": self.client.model,
            "api_base": self.client.api_base,
            "timestamp": datetime.now().isoformat(),
            "tests": []
        }
        
        for i, prompt in enumerate(test_prompts, 1):
            print(f"\n🧪 Тест {i}/{len(test_prompts)}: {prompt[:50]}...")
            
            avg_time, median_time, times = self.measure_response_time(prompt)
            
            test_result = {
                "prompt": prompt,
                "avg_time": avg_time,
                "median_time": median_time,
                "times": times,
                "success_rate": len(times) / 3  # Из 3 попыток
            }
            
            results["tests"].append(test_result)
            
            print(f"⏱️ Среднее время: {avg_time:.2f}s")
            print(f"📊 Медиана: {median_time:.2f}s")
        
        return results


def interactive_model_selector(client: LocalGPTClient) -> Optional[str]:
    """
    Интерактивный выбор модели
    
    Args:
        client: Клиент для работы с API
        
    Returns:
        ID выбранной модели или None
    """
    manager = ModelManager(client)
    models = manager.get_available_models()
    
    if not models:
        print("❌ Модели не найдены")
        return None
    
    print("📋 Доступные модели:")
    print("-" * 50)
    
    for i, model in enumerate(models, 1):
        model_id = model.get('id', 'N/A')
        print(f"{i:2d}. {model_id}")
    
    print(f"{len(models)+1:2d}. Отмена")
    
    while True:
        try:
            choice = input(f"\nВыберите модель (1-{len(models)+1}): ").strip()
            
            if not choice:
                continue
            
            choice_num = int(choice)
            
            if choice_num == len(models) + 1:
                print("Отмена выбора модели")
                return None
            
            if 1 <= choice_num <= len(models):
                selected_model = models[choice_num - 1]['id']
                print(f"✅ Выбрана модель: {selected_model}")
                return selected_model
            else:
                print(f"❌ Неверный выбор. Введите число от 1 до {len(models)+1}")
                
        except ValueError:
            print("❌ Введите корректное число")
        except KeyboardInterrupt:
            print("\nОтмена выбора модели")
            return None


def main():
    """Демонстрация утилит"""
    print("🛠️ Демонстрация утилит LocalGPT")
    
    client = create_default_client()
    
    # Тест менеджера моделей
    print("\n1️⃣ Информация о моделях:")
    manager = ModelManager(client)
    manager.print_models_info()
    
    # Тест логгера
    print("\n2️⃣ Тест логгера:")
    logger = ConversationLogger()
    session_id = logger.start_session("demo")
    logger.log_message("user", "Привет!", client.model, client.api_base)
    logger.log_message("assistant", "Привет! Как дела?", client.model, client.api_base)
    
    log_file = logger.save_session()
    print(f"💾 Лог сохранен: {log_file}")
    
    # Тест бенчмарка (быстрый)
    print("\n3️⃣ Быстрый бенчмарк:")
    benchmark = ModelBenchmark(client)
    results = benchmark.run_benchmark(["Привет!"])
    
    avg_time = results["tests"][0]["avg_time"]
    print(f"⚡ Среднее время ответа: {avg_time:.2f}s")


if __name__ == "__main__":
    main()
