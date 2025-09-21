"""
Менеджер промптов для системы анализа JIRA задач
Версия 0.3 - гибкое управление промптами
"""

import os
import yaml
from typing import Dict, Any, Optional
from pathlib import Path


class PromptManager:
    """Менеджер для управления промптами различных этапов pipeline"""
    
    def __init__(self, prompts_dir: str = "prompts"):
        """
        Инициализация менеджера промптов
        
        Args:
            prompts_dir: Путь к папке с промптами
        """
        self.prompts_dir = Path(prompts_dir)
        self.configs = {}
        self.active_prompts = {}
        
    def load_category_generation_config(self) -> Dict[str, Any]:
        """Загружает конфигурацию промптов для генерации категорий"""
        config_path = self.prompts_dir / "category_generation" / "config.yaml"
        
        if not config_path.exists():
            raise FileNotFoundError(f"Конфигурационный файл не найден: {config_path}")
            
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
            
        self.configs['category_generation'] = config
        return config
    
    def get_category_generation_prompt(self, prompt_name: Optional[str] = None) -> str:
        """
        Получает промпт для генерации категорий
        
        Args:
            prompt_name: Название промпта (если None, используется активный)
            
        Returns:
            Текст промпта
        """
        if 'category_generation' not in self.configs:
            self.load_category_generation_config()
            
        config = self.configs['category_generation']
        
        # Определяем какой промпт использовать
        if prompt_name is None:
            prompt_name = config.get('active_prompt', 'basic_v1')
            
        if prompt_name not in config['prompts']:
            available = list(config['prompts'].keys())
            raise ValueError(f"Промпт '{prompt_name}' не найден. Доступные: {available}")
            
        prompt_config = config['prompts'][prompt_name]
        prompt_file = prompt_config['file']
        
        # Загружаем текст промпта из файла
        prompt_path = self.prompts_dir / "category_generation" / prompt_file
        
        if not prompt_path.exists():
            raise FileNotFoundError(f"Файл промпта не найден: {prompt_path}")
            
        with open(prompt_path, 'r', encoding='utf-8') as f:
            prompt_text = f.read().strip()
            
        return prompt_text
    
    def get_category_generation_parameters(self, prompt_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Получает параметры для промпта генерации категорий
        
        Args:
            prompt_name: Название промпта (если None, используется активный)
            
        Returns:
            Словарь с параметрами промпта
        """
        if 'category_generation' not in self.configs:
            self.load_category_generation_config()
            
        config = self.configs['category_generation']
        
        if prompt_name is None:
            prompt_name = config.get('active_prompt', 'basic_v1')
            
        if prompt_name not in config['prompts']:
            available = list(config['prompts'].keys())
            raise ValueError(f"Промпт '{prompt_name}' не найден. Доступные: {available}")
            
        return config['prompts'][prompt_name].get('parameters', {})
    
    def list_category_generation_prompts(self) -> Dict[str, Dict[str, str]]:
        """
        Возвращает список доступных промптов для генерации категорий
        
        Returns:
            Словарь {prompt_name: {name, description}}
        """
        if 'category_generation' not in self.configs:
            self.load_category_generation_config()
            
        config = self.configs['category_generation']
        
        result = {}
        for prompt_name, prompt_config in config['prompts'].items():
            result[prompt_name] = {
                'name': prompt_config.get('name', prompt_name),
                'description': prompt_config.get('description', 'Описание отсутствует')
            }
            
        return result
    
    def set_active_category_generation_prompt(self, prompt_name: str) -> None:
        """
        Устанавливает активный промпт для генерации категорий
        
        Args:
            prompt_name: Название промпта
        """
        if 'category_generation' not in self.configs:
            self.load_category_generation_config()
            
        config = self.configs['category_generation']
        
        if prompt_name not in config['prompts']:
            available = list(config['prompts'].keys())
            raise ValueError(f"Промпт '{prompt_name}' не найден. Доступные: {available}")
            
        config['active_prompt'] = prompt_name
        
        # Сохраняем изменения в конфигурационный файл
        config_path = self.prompts_dir / "category_generation" / "config.yaml"
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True)
            
        print(f"✅ Активный промпт для генерации категорий изменен на: {prompt_name}")
    
    def format_category_generation_prompt(self, tasks_text: str, prompt_name: Optional[str] = None, existing_categories: Optional[list] = None) -> str:
        """
        Форматирует промпт для генерации категорий с подстановкой данных
        
        Args:
            tasks_text: Текст задач для анализа
            prompt_name: Название промпта (если None, используется активный)
            existing_categories: Список уже существующих категорий для контекста
            
        Returns:
            Отформатированный промпт
        """
        prompt_template = self.get_category_generation_prompt(prompt_name)
        parameters = self.get_category_generation_parameters(prompt_name)
        
        # Формируем секцию с существующими категориями
        existing_categories_section = ""
        if existing_categories and len(existing_categories) > 0:
            existing_categories_section = "\n"
            for i, cat in enumerate(existing_categories, 1):
                existing_categories_section += f"{i}. Категория: {cat.get('Название', '')}\nОписание: {cat.get('Описание', '')}\n"
                if cat.get('Ключевые_слова'):
                    existing_categories_section += f"   Ключевые слова: {cat['Ключевые_слова']}\n"
                if cat.get('Типы_задач'):
                    existing_categories_section += f"   Типы задач: {cat['Типы_задач']}\n"
                existing_categories_section += "\n"
        
        # Подставляем параметры в шаблон
        format_vars = {
            'tasks_text': tasks_text,
            'existing_categories_section': existing_categories_section,
            'max_categories': parameters.get('max_categories', 10),
            **parameters
        }
        
        try:
            formatted_prompt = prompt_template.format(**format_vars)
            return formatted_prompt
        except KeyError as e:
            raise ValueError(f"Ошибка форматирования промпта: отсутствует переменная {e}")
    
    def load_category_consolidation_config(self) -> Dict[str, Any]:
        """Загружает конфигурацию промптов для консолидации категорий"""
        config_path = self.prompts_dir / "category_consolidation" / "config.yaml"
        
        if not config_path.exists():
            raise FileNotFoundError(f"Конфигурационный файл не найден: {config_path}")
            
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
            
        self.configs['category_consolidation'] = config
        return config
    
    def get_category_consolidation_prompt(self, prompt_name: Optional[str] = None) -> str:
        """
        Получает промпт для консолидации категорий
        
        Args:
            prompt_name: Название промпта (если None, используется активный)
            
        Returns:
            Текст промпта
        """
        if 'category_consolidation' not in self.configs:
            self.load_category_consolidation_config()
            
        config = self.configs['category_consolidation']
        
        # Определяем какой промпт использовать
        if prompt_name is None:
            prompt_name = config.get('active_prompt', 'basic_v1')
            
        if prompt_name not in config['prompts']:
            available = list(config['prompts'].keys())
            raise ValueError(f"Промпт '{prompt_name}' не найден. Доступные: {available}")
            
        prompt_config = config['prompts'][prompt_name]
        prompt_file = prompt_config['file']
        
        # Загружаем текст промпта из файла
        prompt_path = self.prompts_dir / "category_consolidation" / prompt_file
        
        if not prompt_path.exists():
            raise FileNotFoundError(f"Файл промпта не найден: {prompt_path}")
            
        with open(prompt_path, 'r', encoding='utf-8') as f:
            return f.read()
    
    def get_category_consolidation_parameters(self, prompt_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Получает параметры промпта для консолидации категорий
        
        Args:
            prompt_name: Название промпта (если None, используется активный)
            
        Returns:
            Словарь параметров
        """
        if 'category_consolidation' not in self.configs:
            self.load_category_consolidation_config()
            
        config = self.configs['category_consolidation']
        
        # Определяем какой промпт использовать
        if prompt_name is None:
            prompt_name = config.get('active_prompt', 'basic_v1')
            
        if prompt_name not in config['prompts']:
            available = list(config['prompts'].keys())
            raise ValueError(f"Промпт '{prompt_name}' не найден. Доступные: {available}")
            
        return config['prompts'][prompt_name].get('parameters', {})
    
    def list_category_consolidation_prompts(self) -> Dict[str, Dict[str, str]]:
        """
        Возвращает список доступных промптов для консолидации категорий
        
        Returns:
            Словарь с информацией о промптах
        """
        if 'category_consolidation' not in self.configs:
            self.load_category_consolidation_config()
            
        config = self.configs['category_consolidation']
        result = {}
        
        for prompt_name, prompt_info in config['prompts'].items():
            result[prompt_name] = {
                'name': prompt_info.get('name', prompt_name),
                'description': prompt_info.get('description', 'Описание отсутствует'),
                'file': prompt_info.get('file', ''),
                'parameters': prompt_info.get('parameters', {})
            }
            
        return result
    
    def set_active_category_consolidation_prompt(self, prompt_name: str) -> None:
        """
        Устанавливает активный промпт для консолидации категорий
        
        Args:
            prompt_name: Название промпта
        """
        if 'category_consolidation' not in self.configs:
            self.load_category_consolidation_config()
            
        config = self.configs['category_consolidation']
        
        if prompt_name not in config['prompts']:
            available = list(config['prompts'].keys())
            raise ValueError(f"Промпт '{prompt_name}' не найден. Доступные: {available}")
            
        config['active_prompt'] = prompt_name
        
        # Сохраняем изменения в конфигурационный файл
        config_path = self.prompts_dir / "category_consolidation" / "config.yaml"
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True)
            
        print(f"✅ Активный промпт для консолидации категорий изменен на: {prompt_name}")
    
    def format_category_consolidation_prompt(self, categories_text: str, target_count: int, prompt_name: Optional[str] = None) -> str:
        """
        Форматирует промпт для консолидации категорий с подстановкой данных
        
        Args:
            categories_text: Текст категорий для консолидации
            target_count: Целевое количество категорий
            prompt_name: Название промпта (если None, используется активный)
            
        Returns:
            Отформатированный промпт
        """
        prompt_template = self.get_category_consolidation_prompt(prompt_name)
        parameters = self.get_category_consolidation_parameters(prompt_name)
        
        # Подставляем параметры в шаблон
        format_vars = {
            'categories_text': categories_text,
            'target_count': target_count,
            **parameters
        }
        
        try:
            return prompt_template.format(**format_vars)
        except KeyError as e:
            raise ValueError(f"Ошибка форматирования промпта: отсутствует переменная {e}")


def create_category_prompt_manager() -> PromptManager:
    """Создает и возвращает менеджер промптов для генерации категорий"""
    return PromptManager()


if __name__ == "__main__":
    # Тестирование менеджера промптов
    manager = create_category_prompt_manager()
    
    print("🔧 Тестирование PromptManager")
    print("\n📋 Доступные промпты:")
    prompts = manager.list_category_generation_prompts()
    for name, info in prompts.items():
        print(f"  - {name}: {info['name']}")
        print(f"    {info['description']}")
    
    print(f"\n🎯 Активный промпт: {manager.configs.get('category_generation', {}).get('active_prompt', 'не загружен')}")
    
    # Тест получения промпта
    try:
        prompt = manager.get_category_generation_prompt()
        print(f"\n✅ Промпт загружен успешно ({len(prompt)} символов)")
        
        # Тест форматирования
        test_tasks = "Тестовая задача для проверки форматирования"
        formatted = manager.format_category_generation_prompt(test_tasks)
        print(f"✅ Промпт отформатирован успешно ({len(formatted)} символов)")
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
