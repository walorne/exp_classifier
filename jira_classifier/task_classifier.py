"""
Модуль для классификации задач с оценкой релевантности
"""

import re
import json
from typing import List, Dict, Tuple, Optional
import logging
from clients.client import LocalGPTClient
from .models import JiraTask, Category, ClassificationResult

logger = logging.getLogger(__name__)


class TaskClassifier:
    """Классификатор задач с использованием LLM"""
    
    def __init__(self, llm_client: LocalGPTClient, confidence_threshold: int = 50):
        """
        Инициализация классификатора
        
        Args:
            llm_client: Клиент для работы с LLM
            confidence_threshold: Порог уверенности для классификации
        """
        self.llm_client = llm_client
        self.confidence_threshold = confidence_threshold
    
    def classify_tasks(self, tasks: List[JiraTask], 
                      categories: List[Category],
                      batch_size: int = 10) -> List[ClassificationResult]:
        """
        Классификация списка задач
        
        Args:
            tasks: Список задач для классификации
            categories: Список категорий
            batch_size: Размер батча для обработки
        
        Returns:
            Список результатов классификации
        """
        logger.info(f"Начинаем классификацию {len(tasks)} задач по {len(categories)} категориям")
        
        results = []
        
        # Обрабатываем задачи батчами для оптимизации
        for i in range(0, len(tasks), batch_size):
            batch = tasks[i:i + batch_size]
            logger.info(f"Обрабатываем батч {i//batch_size + 1}/{(len(tasks) + batch_size - 1)//batch_size}")
            
            batch_results = self._classify_batch(batch, categories)
            results.extend(batch_results)
        
        # Обрабатываем задачи с низкой уверенностью
        low_confidence_results = [r for r in results if r.confidence < self.confidence_threshold]
        if low_confidence_results:
            logger.info(f"Повторная обработка {len(low_confidence_results)} задач с низкой уверенностью")
            improved_results = self._reclassify_low_confidence(
                [tasks[i] for i, r in enumerate(results) if r.confidence < self.confidence_threshold],
                categories,
                low_confidence_results
            )
            
            # Заменяем результаты с низкой уверенностью на улучшенные
            improved_dict = {r.task_id: r for r in improved_results}
            for i, result in enumerate(results):
                if result.task_id in improved_dict:
                    results[i] = improved_dict[result.task_id]
        
        logger.info(f"Классификация завершена. Средняя уверенность: {sum(r.confidence for r in results) / len(results):.1f}%")
        return results
    
    def _classify_batch(self, tasks: List[JiraTask], 
                       categories: List[Category]) -> List[ClassificationResult]:
        """
        Классификация батча задач
        
        Args:
            tasks: Батч задач
            categories: Список категорий
        
        Returns:
            Результаты классификации батча
        """
        # Подготавливаем промпт для батча
        prompt = self._create_batch_classification_prompt(tasks, categories)
        
        # Отправляем запрос к LLM
        try:
            response = self.llm_client.simple_chat(prompt)
            return self._parse_batch_response(response, tasks, categories)
        except Exception as e:
            logger.error(f"Ошибка при классификации батча: {e}")
            # Возвращаем результаты с низкой уверенностью
            return [
                ClassificationResult(
                    task_id=task.key,
                    category_scores={cat.name: 0 for cat in categories},
                    final_category=categories[0].name if categories else "Неопределено",
                    confidence=0,
                    reasoning="Ошибка при классификации",
                    alternative_categories=[]
                )
                for task in tasks
            ]
    
    def _create_batch_classification_prompt(self, tasks: List[JiraTask], 
                                          categories: List[Category]) -> str:
        """
        Создание промпта для классификации батча задач
        
        Args:
            tasks: Батч задач
            categories: Список категорий
        
        Returns:
            Промпт для LLM
        """
        # Подготавливаем информацию о категориях
        categories_info = []
        for i, cat in enumerate(categories, 1):
            cat_info = f"""КАТЕГОРИЯ_{i}: {cat.name}
Описание: {cat.description}
Ключевые слова: {', '.join(cat.keywords)}
Типы задач: {', '.join(cat.issue_types)}"""
            categories_info.append(cat_info)
        
        categories_text = "\n\n".join(categories_info)
        
        # Подготавливаем информацию о задачах
        tasks_info = []
        for i, task in enumerate(tasks, 1):
            task_info = f"""ЗАДАЧА_{i}:
ID: {task.key}
Title: {task.title}
Type: {task.issue_type}
Description: {task.description[:300]}{'...' if len(task.description) > 300 else ''}"""
            tasks_info.append(task_info)
        
        tasks_text = "\n\n".join(tasks_info)
        
        return f"""Ты эксперт по классификации IT-задач. Классифицируй каждую задачу по одной из предложенных категорий с оценкой релевантности.

КАТЕГОРИИ:
{categories_text}

ЗАДАЧИ ДЛЯ КЛАССИФИКАЦИИ:
{tasks_text}

ДЛЯ КАЖДОЙ ЗАДАЧИ:
1. Оцени релевантность КАЖДОЙ категории от 0 до 100
2. Выбери категорию с максимальной релевантностью
3. Укажи уверенность в решении (0-100)
4. Дай краткое обоснование

ФОРМАТ ОТВЕТА ДЛЯ КАЖДОЙ ЗАДАЧИ:

ЗАДАЧА_1:
Релевантность:
- {categories[0].name}: [0-100] - [краткое обоснование]
- {categories[1].name if len(categories) > 1 else 'Другая'}: [0-100] - [краткое обоснование]
...
Итоговая_категория: [название категории с максимальной релевантностью]
Уверенность: [0-100]
Обоснование: [почему выбрана именно эта категория]

ЗАДАЧА_2:
...

ВАЖНО: Обязательно классифицируй ВСЕ задачи. Если задача не подходит ни к одной категории, выбери наиболее близкую."""
    
    def _parse_batch_response(self, response: str, tasks: List[JiraTask], 
                            categories: List[Category]) -> List[ClassificationResult]:
        """
        Парсинг ответа LLM для батча задач
        
        Args:
            response: Ответ от LLM
            tasks: Исходные задачи
            categories: Список категорий
        
        Returns:
            Результаты классификации
        """
        results = []
        
        # Разбиваем ответ на блоки для каждой задачи
        task_blocks = re.split(r'ЗАДАЧА_\d+:', response)[1:]  # Убираем первый пустой элемент
        
        for i, (task, block) in enumerate(zip(tasks, task_blocks)):
            try:
                result = self._parse_single_task_response(task.key, block, categories)
                results.append(result)
            except Exception as e:
                logger.warning(f"Ошибка при парсинге ответа для задачи {task.key}: {e}")
                # Создаем результат с низкой уверенностью
                results.append(
                    ClassificationResult(
                        task_id=task.key,
                        category_scores={cat.name: 0 for cat in categories},
                        final_category=categories[0].name if categories else "Неопределено",
                        confidence=0,
                        reasoning="Ошибка при парсинге ответа",
                        alternative_categories=[]
                    )
                )
        
        # Если получили меньше результатов, чем задач, дополняем
        while len(results) < len(tasks):
            missing_task = tasks[len(results)]
            results.append(
                ClassificationResult(
                    task_id=missing_task.key,
                    category_scores={cat.name: 0 for cat in categories},
                    final_category=categories[0].name if categories else "Неопределено",
                    confidence=0,
                    reasoning="Задача не была обработана",
                    alternative_categories=[]
                )
            )
        
        return results
    
    def _parse_single_task_response(self, task_id: str, block: str, 
                                  categories: List[Category]) -> ClassificationResult:
        """
        Парсинг ответа для одной задачи
        
        Args:
            task_id: ID задачи
            block: Блок ответа для задачи
            categories: Список категорий
        
        Returns:
            Результат классификации
        """
        category_scores = {}
        final_category = ""
        confidence = 0
        reasoning = ""
        
        lines = [line.strip() for line in block.split('\n') if line.strip()]
        
        # Парсим релевантность категорий
        in_relevance_section = False
        for line in lines:
            if 'релевантность:' in line.lower():
                in_relevance_section = True
                continue
            
            if in_relevance_section:
                if 'итоговая_категория:' in line.lower():
                    in_relevance_section = False
                    final_category = line.split(':', 1)[1].strip()
                    continue
                
                # Парсим строку с релевантностью
                if ':' in line and '-' in line:
                    parts = line.split(':', 1)
                    if len(parts) == 2:
                        cat_name = parts[0].strip('- ').strip()
                        score_part = parts[1].split('-')[0].strip()
                        try:
                            score = int(score_part)
                            category_scores[cat_name] = score
                        except ValueError:
                            pass
            
            # Парсим уверенность
            if 'уверенность:' in line.lower():
                try:
                    confidence = int(re.search(r'\d+', line).group())
                except (AttributeError, ValueError):
                    confidence = 50
            
            # Парсим обоснование
            if 'обоснование:' in line.lower():
                reasoning = line.split(':', 1)[1].strip()
        
        # Если итоговая категория не найдена, выбираем с максимальным скором
        if not final_category and category_scores:
            final_category = max(category_scores.items(), key=lambda x: x[1])[0]
        
        # Если категория все еще не найдена, берем первую доступную
        if not final_category and categories:
            final_category = categories[0].name
            category_scores[final_category] = 50
        
        # Создаем список альтернативных категорий
        alternative_categories = [
            (cat, score) for cat, score in category_scores.items()
            if cat != final_category and score > 0
        ]
        alternative_categories.sort(key=lambda x: x[1], reverse=True)
        
        return ClassificationResult(
            task_id=task_id,
            category_scores=category_scores,
            final_category=final_category,
            confidence=confidence,
            reasoning=reasoning,
            alternative_categories=alternative_categories
        )
    
    def _reclassify_low_confidence(self, tasks: List[JiraTask], 
                                  categories: List[Category],
                                  original_results: List[ClassificationResult]) -> List[ClassificationResult]:
        """
        Повторная классификация задач с низкой уверенностью
        
        Args:
            tasks: Задачи с низкой уверенностью
            categories: Список категорий
            original_results: Исходные результаты
        
        Returns:
            Улучшенные результаты классификации
        """
        improved_results = []
        
        for task, original_result in zip(tasks, original_results):
            # Создаем более детальный промпт для отдельной задачи
            prompt = self._create_detailed_single_task_prompt(task, categories, original_result)
            
            try:
                response = self.llm_client.simple_chat(prompt)
                result = self._parse_single_task_detailed_response(task.key, response, categories)
                improved_results.append(result)
            except Exception as e:
                logger.warning(f"Ошибка при повторной классификации задачи {task.key}: {e}")
                improved_results.append(original_result)
        
        return improved_results
    
    def _create_detailed_single_task_prompt(self, task: JiraTask, 
                                          categories: List[Category],
                                          original_result: ClassificationResult) -> str:
        """
        Создание детального промпта для одной задачи
        
        Args:
            task: Задача
            categories: Список категорий
            original_result: Исходный результат классификации
        
        Returns:
            Детальный промпт
        """
        categories_info = []
        for cat in categories:
            cat_info = f"""- {cat.name}: {cat.description}
  Ключевые слова: {', '.join(cat.keywords)}
  Типы задач: {', '.join(cat.issue_types)}"""
            categories_info.append(cat_info)
        
        return f"""Ты эксперт по классификации IT-задач. Необходимо более точно классифицировать следующую задачу.

ЗАДАЧА:
ID: {task.key}
Title: {task.title}
Type: {task.issue_type}
Description: {task.description}
Labels: {', '.join(task.labels)}
Components: {', '.join(task.components)}
Time Spent: {task.time_spent_hours():.1f} hours

ДОСТУПНЫЕ КАТЕГОРИИ:
{chr(10).join(categories_info)}

ПРЕДЫДУЩАЯ КЛАССИФИКАЦИЯ:
Категория: {original_result.final_category}
Уверенность: {original_result.confidence}%
Обоснование: {original_result.reasoning}

ПРОАНАЛИЗИРУЙ ЗАДАЧУ БОЛЕЕ ДЕТАЛЬНО:
1. Внимательно изучи заголовок, описание и метаданные задачи
2. Определи основную цель и тип выполняемой работы
3. Сопоставь с характеристиками каждой категории
4. Обрати внимание на ключевые слова и контекст

ОТВЕТ В ФОРМАТЕ:
Анализ: [детальный анализ содержимого задачи]
Релевантность_категорий:
{chr(10).join([f"- {cat.name}: [0-100] - [обоснование]" for cat in categories])}
Итоговая_категория: [название]
Уверенность: [0-100]
Обоснование: [подробное объяснение выбора]"""
    
    def _parse_single_task_detailed_response(self, task_id: str, response: str, 
                                           categories: List[Category]) -> ClassificationResult:
        """
        Парсинг детального ответа для одной задачи
        
        Args:
            task_id: ID задачи
            response: Ответ от LLM
            categories: Список категорий
        
        Returns:
            Результат классификации
        """
        # Используем тот же парсер, что и для обычных ответов
        return self._parse_single_task_response(task_id, response, categories)
