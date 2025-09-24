"""
Модели данных для классификации JIRA задач
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from datetime import datetime


@dataclass
class JiraTask:
    """Модель JIRA задачи"""
    key: str                    # Ключ задачи (например, PROJ-123)
    title: str                  # Заголовок задачи
    description: str            # Описание задачи
    issue_type: str            # Тип задачи (Bug, Task, Story, etc.)
    status: str                # Статус задачи
    assignee: Optional[str]    # Исполнитель
    reporter: str              # Создатель
    created: datetime          # Дата создания
    updated: datetime          # Дата обновления
    resolved: Optional[datetime] # Дата решения
    time_spent: int            # Потраченное время в секундах
    original_estimate: Optional[int] # Первоначальная оценка в секундах
    labels: List[str]          # Метки
    components: List[str]      # Компоненты
    priority: str              # Приоритет
    
    def get_content_for_analysis(self) -> str:
        """Получить содержимое задачи для анализа"""
        return f"{self.title}\n\n{self.description}"
    
    def time_spent_hours(self) -> float:
        """Потраченное время в часах"""
        return self.time_spent / 3600 if self.time_spent else 0.0


@dataclass
class Category:
    """Модель категории для классификации"""
    id: str                    # Уникальный идентификатор
    name: str                  # Название категории
    description: str           # Описание категории
    keywords: List[str]        # Ключевые слова
    issue_types: List[str]     # Подходящие типы задач
    examples: List[str]        # Примеры задач
    
    def to_dict(self) -> Dict:
        """Преобразование в словарь"""
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'keywords': self.keywords,
            'issue_types': self.issue_types,
            'examples': self.examples
        }


@dataclass
class ClassificationResult:
    """Результат классификации задачи"""
    task_id: str                           # ID задачи
    category_scores: Dict[str, int]        # категория -> релевантность (0-100)
    final_category: str                    # Итоговая категория
    confidence: int                        # Уверенность в классификации (0-100)
    reasoning: str                         # Обоснование выбора
    alternative_categories: List[Tuple[str, int]]  # Альтернативные категории
    
    def get_top_alternatives(self, limit: int = 3) -> List[Tuple[str, int]]:
        """Получить топ альтернативных категорий"""
        sorted_scores = sorted(
            [(cat, score) for cat, score in self.category_scores.items() 
             if cat != self.final_category and score > 0],
            key=lambda x: x[1], 
            reverse=True
        )
        return sorted_scores[:limit]


@dataclass
class CategoryAnalysisResult:
    """Результат анализа для создания категорий"""
    categories: List[Category]             # Созданные категории
    coverage_analysis: Dict[str, int]      # Анализ покрытия задач
    recommendations: List[str]             # Рекомендации по улучшению


@dataclass
class ClassificationSummary:
    """Сводка по результатам классификации"""
    total_tasks: int                       # Общее количество задач
    categories_count: int                  # Количество категорий
    avg_confidence: float                  # Средняя уверенность
    category_distribution: Dict[str, int]  # Распределение по категориям
    time_spent_by_category: Dict[str, float] # Трудозатраты по категориям
    low_confidence_tasks: List[str]        # Задачи с низкой уверенностью
