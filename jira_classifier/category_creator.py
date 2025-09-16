"""
Модуль для создания категорий классификации с помощью LLM
"""

import json
import re
from typing import List, Dict, Optional
import logging
import random
from clients.client import LocalGPTClient
from .models import JiraTask, Category, CategoryAnalysisResult

logger = logging.getLogger(__name__)


class CategoryCreator:
    """Создатель категорий для классификации задач"""
    
    def __init__(self, llm_client: LocalGPTClient, max_categories: int = 25):
        """
        Инициализация создателя категорий
        
        Args:
            llm_client: Клиент для работы с LLM
            max_categories: Максимальное количество категорий
        """
        self.llm_client = llm_client
        self.max_categories = max_categories
    
    def create_categories(self, tasks: List[JiraTask], 
                         sample_size: int = 200) -> CategoryAnalysisResult:
        """
        Создать категории на основе анализа задач
        
        Args:
            tasks: Список всех задач
            sample_size: Размер выборки для анализа
        
        Returns:
            Результат анализа с созданными категориями
        """
        logger.info(f"Начинаем создание категорий для {len(tasks)} задач")
        
        # Создаем репрезентативную выборку
        sample_tasks = self._create_representative_sample(tasks, sample_size)
        logger.info(f"Создана выборка из {len(sample_tasks)} задач")
        
        # Анализируем выборку и создаем категории
        categories = self._analyze_and_create_categories(sample_tasks)
        logger.info(f"Создано {len(categories)} категорий")
        
        # Проводим анализ покрытия на всех задачах
        coverage_analysis = self._analyze_coverage(tasks, categories)
        
        # Генерируем рекомендации
        recommendations = self._generate_recommendations(coverage_analysis, categories)
        
        return CategoryAnalysisResult(
            categories=categories,
            coverage_analysis=coverage_analysis,
            recommendations=recommendations
        )
    
    def _create_representative_sample(self, tasks: List[JiraTask], 
                                    sample_size: int) -> List[JiraTask]:
        """
        Создать репрезентативную выборку задач
        
        Args:
            tasks: Все задачи
            sample_size: Размер выборки
        
        Returns:
            Выборка задач
        """
        if len(tasks) <= sample_size:
            return tasks
        
        # Группируем по типам задач для репрезентативности
        tasks_by_type = {}
        for task in tasks:
            if task.issue_type not in tasks_by_type:
                tasks_by_type[task.issue_type] = []
            tasks_by_type[task.issue_type].append(task)
        
        # Берем пропорциональную выборку из каждого типа
        sample = []
        for issue_type, type_tasks in tasks_by_type.items():
            type_sample_size = max(1, int(len(type_tasks) / len(tasks) * sample_size))
            type_sample = random.sample(type_tasks, min(type_sample_size, len(type_tasks)))
            sample.extend(type_sample)
        
        # Если выборка получилась меньше нужного размера, дополняем случайными задачами
        if len(sample) < sample_size:
            remaining_tasks = [t for t in tasks if t not in sample]
            additional_needed = sample_size - len(sample)
            if remaining_tasks:
                additional = random.sample(remaining_tasks, 
                                         min(additional_needed, len(remaining_tasks)))
                sample.extend(additional)
        
        return sample[:sample_size]
    
    def _analyze_and_create_categories(self, tasks: List[JiraTask]) -> List[Category]:
        """
        Анализ задач и создание категорий через LLM
        
        Args:
            tasks: Выборка задач для анализа
        
        Returns:
            Список созданных категорий
        """
        # Подготавливаем данные для анализа
        tasks_summary = self._prepare_tasks_for_analysis(tasks)
        
        # Создаем промпт для LLM
        prompt = self._create_analysis_prompt(tasks_summary)
        
        # Отправляем запрос к LLM
        logger.info("Отправляем запрос к LLM для создания категорий...")
        response = self.llm_client.simple_chat(prompt)
        
        # Парсим ответ и создаем категории
        categories = self._parse_categories_response(response)
        
        logger.info(f"LLM создал {len(categories)} категорий")
        return categories
    
    def _prepare_tasks_for_analysis(self, tasks: List[JiraTask]) -> str:
        """
        Подготовить задачи для анализа LLM
        
        Args:
            tasks: Список задач
        
        Returns:
            Отформатированный текст с задачами
        """
        tasks_text = []
        for i, task in enumerate(tasks, 1):
            task_text = f"""{i}. ID: {task.key}
   Title: {task.title}
   Type: {task.issue_type}
   Description: {task.description[:200]}{'...' if len(task.description) > 200 else ''}
   Time Spent: {task.time_spent_hours():.1f}h

"""
            tasks_text.append(task_text)
        
        return "\n".join(tasks_text)
    
    def _create_analysis_prompt(self, tasks_summary: str) -> str:
        """
        Создать промпт для анализа задач
        
        Args:
            tasks_summary: Сводка по задачам
        
        Returns:
            Промпт для LLM
        """
        return f"""Ты эксперт по анализу IT-процессов и рабочих задач. Проанализируй следующие JIRA задачи и создай систему категорий для их классификации.

ТРЕБОВАНИЯ:
1. Создай не более {self.max_categories} категорий
2. Каждая категория должна объединять логически связанные задачи
3. Категории должны покрывать ВСЕ типы деятельности из выборки
4. Названия категорий должны быть понятными и отражать суть работы
5. Избегай слишком узких или слишком широких категорий

ЗАДАЧИ ДЛЯ АНАЛИЗА:
{tasks_summary}

ПРОАНАЛИЗИРУЙ И ОПРЕДЕЛИ:
1. Какие ТИПЫ ДЕЯТЕЛЬНОСТИ повторяются в задачах?
2. Какие ПАТТЕРНЫ можно выделить в заголовках и описаниях?
3. Как можно СГРУППИРОВАТЬ задачи по смыслу выполняемой работы?

СОЗДАЙ КАТЕГОРИИ В СЛЕДУЮЩЕМ ФОРМАТЕ:

КАТЕГОРИЯ_1:
Название: [Краткое название категории]
Описание: [Что входит в эту категорию, какие типы работ]
Ключевые_слова: [слова и фразы, которые характерны для этой категории, через запятую]
Типы_задач: [какие issue types обычно относятся к этой категории, через запятую]
Примеры: [номера задач из списка выше, которые относятся к этой категории]

КАТЕГОРИЯ_2:
...

Обязательно проанализируй ВСЕ задачи и убедись, что каждая задача может быть отнесена к одной из созданных категорий."""
    
    def _parse_categories_response(self, response: str) -> List[Category]:
        """
        Парсинг ответа LLM с категориями
        
        Args:
            response: Ответ от LLM
        
        Returns:
            Список категорий
        """
        categories = []
        
        # Ищем блоки категорий в ответе
        category_pattern = r"КАТЕГОРИЯ_\d+:\s*\n(.*?)(?=КАТЕГОРИЯ_\d+:|$)"
        category_blocks = re.findall(category_pattern, response, re.DOTALL | re.IGNORECASE)
        
        for i, block in enumerate(category_blocks, 1):
            try:
                category = self._parse_single_category(block, f"cat_{i}")
                if category:
                    categories.append(category)
            except Exception as e:
                logger.warning(f"Ошибка при парсинге категории {i}: {e}")
                continue
        
        # Если не удалось распарсить через регулярки, пробуем построчно
        if not categories:
            categories = self._parse_categories_fallback(response)
        
        return categories
    
    def _parse_single_category(self, block: str, category_id: str) -> Optional[Category]:
        """
        Парсинг одной категории из блока текста
        
        Args:
            block: Текстовый блок с информацией о категории
            category_id: ID категории
        
        Returns:
            Объект Category или None
        """
        lines = [line.strip() for line in block.split('\n') if line.strip()]
        
        name = ""
        description = ""
        keywords = []
        issue_types = []
        examples = []
        
        for line in lines:
            if line.lower().startswith('название:'):
                name = line.split(':', 1)[1].strip()
            elif line.lower().startswith('описание:'):
                description = line.split(':', 1)[1].strip()
            elif line.lower().startswith('ключевые_слова:') or line.lower().startswith('ключевые слова:'):
                keywords_text = line.split(':', 1)[1].strip()
                keywords = [kw.strip() for kw in keywords_text.split(',') if kw.strip()]
            elif line.lower().startswith('типы_задач:') or line.lower().startswith('типы задач:'):
                types_text = line.split(':', 1)[1].strip()
                issue_types = [t.strip() for t in types_text.split(',') if t.strip()]
            elif line.lower().startswith('примеры:'):
                examples_text = line.split(':', 1)[1].strip()
                examples = [ex.strip() for ex in examples_text.split(',') if ex.strip()]
        
        if name and description:
            return Category(
                id=category_id,
                name=name,
                description=description,
                keywords=keywords,
                issue_types=issue_types,
                examples=examples
            )
        
        return None
    
    def _parse_categories_fallback(self, response: str) -> List[Category]:
        """
        Резервный способ парсинга категорий
        
        Args:
            response: Ответ от LLM
        
        Returns:
            Список категорий
        """
        logger.warning("Используем резервный способ парсинга категорий")
        
        # Простой способ - ищем строки с названиями категорий
        lines = response.split('\n')
        categories = []
        current_category = None
        category_counter = 1
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Ищем начало новой категории
            if 'название:' in line.lower() or (line and not line.startswith(' ') and ':' not in line):
                if current_category:
                    categories.append(current_category)
                
                name = line.replace('Название:', '').replace('название:', '').strip()
                if not name:
                    name = f"Категория {category_counter}"
                
                current_category = Category(
                    id=f"cat_{category_counter}",
                    name=name,
                    description="Автоматически созданная категория",
                    keywords=[],
                    issue_types=[],
                    examples=[]
                )
                category_counter += 1
        
        if current_category:
            categories.append(current_category)
        
        return categories
    
    def _analyze_coverage(self, tasks: List[JiraTask], 
                         categories: List[Category]) -> Dict[str, int]:
        """
        Анализ покрытия задач категориями
        
        Args:
            tasks: Все задачи
            categories: Созданные категории
        
        Returns:
            Словарь с анализом покрытия
        """
        # Простой анализ на основе ключевых слов
        coverage = {}
        uncategorized = 0
        
        for task in tasks:
            task_content = f"{task.title} {task.description}".lower()
            matched = False
            
            for category in categories:
                # Проверяем наличие ключевых слов
                for keyword in category.keywords:
                    if keyword.lower() in task_content:
                        if category.name not in coverage:
                            coverage[category.name] = 0
                        coverage[category.name] += 1
                        matched = True
                        break
                
                if matched:
                    break
            
            if not matched:
                uncategorized += 1
        
        coverage['Неклассифицированные'] = uncategorized
        return coverage
    
    def _generate_recommendations(self, coverage: Dict[str, int], 
                                categories: List[Category]) -> List[str]:
        """
        Генерация рекомендаций по улучшению классификации
        
        Args:
            coverage: Анализ покрытия
            categories: Созданные категории
        
        Returns:
            Список рекомендаций
        """
        recommendations = []
        
        total_tasks = sum(coverage.values())
        uncategorized = coverage.get('Неклассифицированные', 0)
        
        if uncategorized > total_tasks * 0.1:  # Более 10% неклассифицированных
            recommendations.append(
                f"Высокий процент неклассифицированных задач ({uncategorized}/{total_tasks}, "
                f"{uncategorized/total_tasks*100:.1f}%). Рекомендуется пересмотреть ключевые слова категорий."
            )
        
        # Проверяем категории с малым покрытием
        for category_name, count in coverage.items():
            if category_name != 'Неклассифицированные' and count < total_tasks * 0.02:  # Менее 2%
                recommendations.append(
                    f"Категория '{category_name}' имеет очень мало задач ({count}). "
                    f"Возможно, стоит объединить её с другой категорией."
                )
        
        if len(categories) > 20:
            recommendations.append(
                f"Создано {len(categories)} категорий. Рекомендуется объединить похожие категории "
                f"для упрощения классификации."
            )
        
        return recommendations
