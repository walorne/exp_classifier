"""
Клиент для подключения к модели Qwen3-Coder через LiteLLM API
"""
import requests
import json
from typing import Dict, List, Optional, Any


class LocalGPTClient:
    """Клиент для работы с моделью Qwen3-Coder через OpenAI-совместимый API"""
    
    def __init__(self, api_base: str, api_key: str, model: str):
        """
        Инициализация клиента
        
        Args:
            api_base: Базовый URL API (например: http://sm-litellm.gksm.local)
            api_key: API ключ для аутентификации
            model: Название модели (например: Cloud.ru/Qwen3-Coder-480B-A35B-Instruct)
        """
        self.api_base = api_base.rstrip('/')
        self.api_key = api_key
        self.model = model
        
        # Заголовки для запросов
        self.headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }
    
    def chat_completion(
        self, 
        messages: List[Dict[str, str]], 
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Отправка запроса для генерации текста
        
        Args:
            messages: Список сообщений в формате OpenAI
            temperature: Температура генерации (0.0-2.0)
            max_tokens: Максимальное количество токенов в ответе
            stream: Использовать потоковую передачу
            **kwargs: Дополнительные параметры
            
        Returns:
            Ответ от API в формате OpenAI
            
        Raises:
            requests.RequestException: При ошибке HTTP запроса
            ValueError: При неверных параметрах
        """
        url = f"{self.api_base}/v1/chat/completions"
        
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": stream,
            **kwargs
        }
        
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        
        try:
            response = requests.post(
                url, 
                headers=self.headers, 
                json=payload,
                timeout=240
            )
            response.raise_for_status()
            
            if stream:
                return response
            else:
                return response.json()
                
        except requests.RequestException as e:
            raise requests.RequestException(f"Ошибка при запросе к API: {e}")
    
    def simple_chat(self, prompt: str, system_message: Optional[str] = None) -> str:
        """
        Упрощенный метод для отправки текстового запроса
        
        Args:
            prompt: Пользовательский запрос
            system_message: Системное сообщение (опционально)
            
        Returns:
            Текст ответа от модели
        """
        messages = []
        
        if system_message:
            messages.append({"role": "system", "content": system_message})
        
        messages.append({"role": "user", "content": prompt})
        
        response = self.chat_completion(messages)
        
        try:
            return response["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as e:
            raise ValueError(f"Неожиданный формат ответа от API: {e}")
    
    def get_models(self) -> List[Dict[str, Any]]:
        """
        Получение списка доступных моделей
        
        Returns:
            Список доступных моделей
        """
        url = f"{self.api_base}/v1/models"
        
        try:
            response = requests.get(url, headers=self.headers, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            raise requests.RequestException(f"Ошибка при получении списка моделей: {e}")
    
    def health_check(self) -> bool:
        """
        Проверка доступности API
        
        Returns:
            True если API доступен, False в противном случае
        """
        try:
            self.get_models()
            return True
        except:
            return False
    
    def get_model_info(self, model_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Получить информацию о модели
        
        Args:
            model_name: Название модели (если не указано, используется текущая)
            
        Returns:
            Словарь с информацией о модели
        """
        target_model = model_name or self.model
        
        try:
            # Получаем базовую информацию из /v1/models
            models = self.get_models()
            
            # Ищем нужную модель
            model_info = None
            for model in models.get('data', []):
                if model.get('id') == target_model:
                    model_info = model
                    break
            
            if not model_info:
                return {'error': f'Модель {target_model} не найдена'}
            
            # Пробуем получить расширенную информацию
            extended_info = self._get_extended_model_info(target_model)
            
            # Объединяем базовую и расширенную информацию
            result = {
                'id': model_info.get('id'),
                'object': model_info.get('object'),
                'created': model_info.get('created'),
                'owned_by': model_info.get('owned_by'),
                # Все возможные поля из ответа
                **{k: v for k, v in model_info.items() if k not in ['id', 'object', 'created', 'owned_by']},
                # Расширенная информация
                **extended_info
            }
            
            return result
                
        except Exception as e:
            return {'error': f'Ошибка получения информации о модели: {e}'}
    
    def _get_extended_model_info(self, model_name: str) -> Dict[str, Any]:
        """
        Попытка получить расширенную информацию о модели
        
        Args:
            model_name: Название модели
            
        Returns:
            Словарь с дополнительной информацией
        """
        extended_info = {}
        
        try:
            # Пробуем разные эндпоинты для получения информации
            endpoints_to_try = [
                f"/v1/models/{model_name}",
                f"/model/{model_name}",
                f"/models/{model_name}/info",
                "/health"
            ]
            
            for endpoint in endpoints_to_try:
                try:
                    url = f"{self.api_base}{endpoint}"
                    response = requests.get(url, headers=self.headers, timeout=10)
                    if response.status_code == 200:
                        data = response.json()
                        
                        # Извлекаем полезную информацию
                        if 'context_length' in data:
                            extended_info['context_length'] = data['context_length']
                        if 'max_tokens' in data:
                            extended_info['max_tokens'] = data['max_tokens']
                        if 'max_context_length' in data:
                            extended_info['context_length'] = data['max_context_length']
                            
                        break
                except:
                    continue
            
            # Если не удалось получить, добавляем известные значения для популярных моделей
            if not extended_info.get('context_length'):
                extended_info.update(self._get_known_model_params(model_name))
                
        except Exception:
            pass
            
        return extended_info
    
    def _get_known_model_params(self, model_name: str) -> Dict[str, Any]:
        """
        Известные параметры для популярных моделей
        
        Args:
            model_name: Название модели
            
        Returns:
            Словарь с известными параметрами
        """
        known_models = {
            'gpt-3.5-turbo': {'context_length': 4096, 'supports_streaming': True},
            'gpt-4': {'context_length': 8192, 'supports_streaming': True},
            'gpt-4-32k': {'context_length': 32768, 'supports_streaming': True},
            'claude-3-sonnet': {'context_length': 200000, 'supports_streaming': True},
            'claude-3-opus': {'context_length': 200000, 'supports_streaming': True},
        }
        
        # Проверяем точное совпадение
        if model_name in known_models:
            return known_models[model_name]
        
        # Проверяем частичное совпадение
        for known_model, params in known_models.items():
            if known_model.lower() in model_name.lower():
                return params
        
        # Для Qwen моделей - примерные значения
        if 'qwen' in model_name.lower():
            return {
                'context_length': 32768,  # Обычно у Qwen моделей
                'supports_streaming': True,
                'supports_functions': False
            }
            
        return {}
    
    def get_context_window(self) -> int:
        """
        Получить размер контекстного окна модели
        
        Returns:
            Размер контекстного окна в токенах (или -1 если неизвестно)
        """
        model_info = self.get_model_info()
        
        # Пробуем разные поля для размера контекста
        context_size = (
            model_info.get('context_length') or
            model_info.get('max_tokens') or
            model_info.get('context_window') or
            model_info.get('max_context_length')
        )
        
        return context_size if context_size else -1


# Конфигурация по умолчанию из вашего плагина Continue
DEFAULT_CONFIG = {
    "api_base": "http://sm-litellm.gksm.local",
    "api_key": "sk-vNZ2bKnZ0CLG7TvVx3lYOg",
    "model": "Cloud.ru/Qwen3-Coder-480B-A35B-Instruct"
}


def create_default_client() -> LocalGPTClient:
    """Создание клиента с конфигурацией по умолчанию"""
    return LocalGPTClient(**DEFAULT_CONFIG)


if __name__ == "__main__":
    # Пример использования
    client = create_default_client()
    
    # Проверка подключения
    if client.health_check():
        print("✅ Подключение к API успешно")
        
        # Тестовый запрос
        response = client.simple_chat("Привет! Как дела?")
        print(f"Ответ модели: {response}")
    else:
        print("❌ Не удалось подключиться к API")

    model_info = client.get_model_info()
    print(model_info)
