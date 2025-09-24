"""
Модуль для создания CSV отчетов для Excel
"""

import csv
import os
from typing import List, Dict, Optional
from datetime import datetime
import logging
from .models import JiraTask, Category, ClassificationResult, ClassificationSummary

logger = logging.getLogger(__name__)


class CSVReporter:
    """Генератор CSV отчетов для анализа классификации"""
    
    def __init__(self, output_dir: str = "reports"):
        """
        Инициализация генератора отчетов
        
        Args:
            output_dir: Директория для сохранения отчетов
        """
        self.output_dir = output_dir
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
    
    def generate_classification_report(self, 
                                     tasks: List[JiraTask],
                                     results: List[ClassificationResult],
                                     categories: List[Category],
                                     filename: Optional[str] = None) -> str:
        """
        Создать основной отчет по классификации
        
        Args:
            tasks: Список задач
            results: Результаты классификации
            categories: Список категорий
            filename: Имя файла (если не указано, генерируется автоматически)
        
        Returns:
            Путь к созданному файлу
        """
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"jira_classification_report_{timestamp}.csv"
        
        filepath = os.path.join(self.output_dir, filename)
        
        # Создаем словарь для быстрого поиска задач
        tasks_dict = {task.key: task for task in tasks}
        
        with open(filepath, 'w', newline='', encoding='utf-8-sig') as csvfile:
            fieldnames = [
                'ID задачи',
                'Заголовок',
                'Описание', 
                'Тип задачи',
                'Статус',
                'Исполнитель',
                'Дата создания',
                'Время (часы)',
                'Приоритет',
                'Компоненты',
                'Метки',
                'Назначенная категория',
                'Уверенность (%)',
                'Обоснование',
                'Альтернативные категории',
                'Релевантность по категориям'
            ]
            
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            for result in results:
                task = tasks_dict.get(result.task_id)
                if not task:
                    logger.warning(f"Задача {result.task_id} не найдена в списке задач")
                    continue
                
                # Форматируем альтернативные категории
                alternatives = "; ".join([
                    f"{cat} ({score}%)" for cat, score in result.alternative_categories[:3]
                ])
                
                # Форматируем релевантность по всем категориям
                relevance_scores = "; ".join([
                    f"{cat}: {score}%" for cat, score in result.category_scores.items()
                ])
                
                # Обрезаем длинные поля для удобства просмотра в Excel
                description = task.description[:500] + "..." if len(task.description) > 500 else task.description
                title = task.title[:100] + "..." if len(task.title) > 100 else task.title
                
                row = {
                    'ID задачи': task.key,
                    'Заголовок': title,
                    'Описание': description,
                    'Тип задачи': task.issue_type,
                    'Статус': task.status,
                    'Исполнитель': task.assignee or '',
                    'Дата создания': task.created.strftime('%Y-%m-%d %H:%M'),
                    'Время (часы)': f"{task.time_spent_hours():.1f}",
                    'Приоритет': task.priority,
                    'Компоненты': "; ".join(task.components),
                    'Метки': "; ".join(task.labels),
                    'Назначенная категория': result.final_category,
                    'Уверенность (%)': result.confidence,
                    'Обоснование': result.reasoning,
                    'Альтернативные категории': alternatives,
                    'Релевантность по категориям': relevance_scores
                }
                
                writer.writerow(row)
        
        logger.info(f"Отчет по классификации сохранен: {filepath}")
        return filepath
    
    def generate_summary_report(self, 
                               tasks: List[JiraTask],
                               results: List[ClassificationResult],
                               categories: List[Category],
                               filename: Optional[str] = None) -> str:
        """
        Создать сводный отчет с аналитикой
        
        Args:
            tasks: Список задач
            results: Результаты классификации
            categories: Список категорий
            filename: Имя файла
        
        Returns:
            Путь к созданному файлу
        """
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"jira_summary_report_{timestamp}.csv"
        
        filepath = os.path.join(self.output_dir, filename)
        
        # Вычисляем статистику по категориям
        category_stats = self._calculate_category_statistics(tasks, results)
        
        with open(filepath, 'w', newline='', encoding='utf-8-sig') as csvfile:
            fieldnames = [
                'Категория',
                'Описание категории',
                'Количество задач',
                'Доля от общего (%)',
                'Общее время (часы)',
                'Среднее время на задачу (часы)',
                'Медианное время на задачу (часы)',
                'Средняя уверенность (%)',
                'Основные типы задач',
                'Ключевые слова'
            ]
            
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            # Сортируем категории по количеству задач
            sorted_stats = sorted(category_stats.items(), key=lambda x: x[1]['count'], reverse=True)
            
            for category_name, stats in sorted_stats:
                # Находим описание категории
                category_desc = ""
                category_keywords = ""
                for cat in categories:
                    if cat.name == category_name:
                        category_desc = cat.description
                        category_keywords = "; ".join(cat.keywords)
                        break
                
                row = {
                    'Категория': category_name,
                    'Описание категории': category_desc,
                    'Количество задач': stats['count'],
                    'Доля от общего (%)': f"{stats['percentage']:.1f}",
                    'Общее время (часы)': f"{stats['total_hours']:.1f}",
                    'Среднее время на задачу (часы)': f"{stats['avg_hours']:.1f}",
                    'Медианное время на задачу (часы)': f"{stats['median_hours']:.1f}",
                    'Средняя уверенность (%)': f"{stats['avg_confidence']:.1f}",
                    'Основные типы задач': "; ".join(stats['top_issue_types']),
                    'Ключевые слова': category_keywords
                }
                
                writer.writerow(row)
        
        logger.info(f"Сводный отчет сохранен: {filepath}")
        return filepath
    
    def generate_low_confidence_report(self,
                                      tasks: List[JiraTask],
                                      results: List[ClassificationResult],
                                      confidence_threshold: int = 70,
                                      filename: Optional[str] = None) -> str:
        """
        Создать отчет по задачам с низкой уверенностью классификации
        
        Args:
            tasks: Список задач
            results: Результаты классификации
            confidence_threshold: Порог уверенности
            filename: Имя файла
        
        Returns:
            Путь к созданному файлу
        """
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"jira_low_confidence_report_{timestamp}.csv"
        
        filepath = os.path.join(self.output_dir, filename)
        
        # Фильтруем результаты с низкой уверенностью
        low_confidence_results = [r for r in results if r.confidence < confidence_threshold]
        
        # Создаем словарь для быстрого поиска задач
        tasks_dict = {task.key: task for task in tasks}
        
        with open(filepath, 'w', newline='', encoding='utf-8-sig') as csvfile:
            fieldnames = [
                'ID задачи',
                'Заголовок',
                'Описание',
                'Тип задачи',
                'Назначенная категория',
                'Уверенность (%)',
                'Обоснование',
                'Топ-3 альтернативы',
                'Рекомендация'
            ]
            
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            for result in low_confidence_results:
                task = tasks_dict.get(result.task_id)
                if not task:
                    continue
                
                # Форматируем топ-3 альтернативы
                top_alternatives = "; ".join([
                    f"{cat} ({score}%)" for cat, score in result.alternative_categories[:3]
                ])
                
                # Генерируем рекомендацию
                recommendation = self._generate_recommendation(result)
                
                row = {
                    'ID задачи': task.key,
                    'Заголовок': task.title[:100] + "..." if len(task.title) > 100 else task.title,
                    'Описание': task.description[:300] + "..." if len(task.description) > 300 else task.description,
                    'Тип задачи': task.issue_type,
                    'Назначенная категория': result.final_category,
                    'Уверенность (%)': result.confidence,
                    'Обоснование': result.reasoning,
                    'Топ-3 альтернативы': top_alternatives,
                    'Рекомендация': recommendation
                }
                
                writer.writerow(row)
        
        logger.info(f"Отчет по задачам с низкой уверенностью сохранен: {filepath} ({len(low_confidence_results)} задач)")
        return filepath
    
    def _calculate_category_statistics(self, 
                                     tasks: List[JiraTask], 
                                     results: List[ClassificationResult]) -> Dict[str, Dict]:
        """
        Вычислить статистику по категориям
        
        Args:
            tasks: Список задач
            results: Результаты классификации
        
        Returns:
            Словарь со статистикой по каждой категории
        """
        # Создаем словарь для быстрого поиска задач
        tasks_dict = {task.key: task for task in tasks}
        
        # Группируем результаты по категориям
        category_data = {}
        
        for result in results:
            category = result.final_category
            task = tasks_dict.get(result.task_id)
            
            if not task:
                continue
            
            if category not in category_data:
                category_data[category] = {
                    'tasks': [],
                    'confidences': [],
                    'hours': [],
                    'issue_types': []
                }
            
            category_data[category]['tasks'].append(task)
            category_data[category]['confidences'].append(result.confidence)
            category_data[category]['hours'].append(task.time_spent_hours())
            category_data[category]['issue_types'].append(task.issue_type)
        
        # Вычисляем статистику
        total_tasks = len(results)
        stats = {}
        
        for category, data in category_data.items():
            count = len(data['tasks'])
            hours = data['hours']
            confidences = data['confidences']
            issue_types = data['issue_types']
            
            # Вычисляем медиану времени
            sorted_hours = sorted([h for h in hours if h > 0])
            median_hours = sorted_hours[len(sorted_hours) // 2] if sorted_hours else 0
            
            # Находим топ типов задач
            issue_type_counts = {}
            for issue_type in issue_types:
                issue_type_counts[issue_type] = issue_type_counts.get(issue_type, 0) + 1
            
            top_issue_types = sorted(issue_type_counts.items(), key=lambda x: x[1], reverse=True)[:3]
            top_issue_types = [f"{itype} ({count})" for itype, count in top_issue_types]
            
            stats[category] = {
                'count': count,
                'percentage': (count / total_tasks) * 100,
                'total_hours': sum(hours),
                'avg_hours': sum(hours) / count if count > 0 else 0,
                'median_hours': median_hours,
                'avg_confidence': sum(confidences) / count if count > 0 else 0,
                'top_issue_types': top_issue_types
            }
        
        return stats
    
    def _generate_recommendation(self, result: ClassificationResult) -> str:
        """
        Генерировать рекомендацию для задачи с низкой уверенностью
        
        Args:
            result: Результат классификации
        
        Returns:
            Текст рекомендации
        """
        if result.confidence < 30:
            return "Требует ручной проверки - очень низкая уверенность"
        elif result.confidence < 50:
            return "Рекомендуется проверить альтернативные категории"
        elif len(result.alternative_categories) > 0:
            top_alt = result.alternative_categories[0]
            if top_alt[1] > result.confidence - 20:  # Если альтернатива близка по скору
                return f"Возможно, больше подходит категория '{top_alt[0]}' ({top_alt[1]}%)"
        
        return "Проверить соответствие категории"
    
    def generate_all_reports(self,
                           tasks: List[JiraTask],
                           results: List[ClassificationResult], 
                           categories: List[Category]) -> Dict[str, str]:
        """
        Создать все типы отчетов
        
        Args:
            tasks: Список задач
            results: Результаты классификации
            categories: Список категорий
        
        Returns:
            Словарь с путями к созданным файлам
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        reports = {}
        
        # Основной отчет
        reports['classification'] = self.generate_classification_report(
            tasks, results, categories, f"classification_report_{timestamp}.csv"
        )
        
        # Сводный отчет
        reports['summary'] = self.generate_summary_report(
            tasks, results, categories, f"summary_report_{timestamp}.csv"
        )
        
        # Отчет по низкой уверенности
        reports['low_confidence'] = self.generate_low_confidence_report(
            tasks, results, 70, f"low_confidence_report_{timestamp}.csv"
        )
        
        logger.info(f"Созданы все отчеты в директории: {self.output_dir}")
        return reports
