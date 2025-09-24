"""
Основной пайплайн для классификации JIRA задач
"""

import json
import logging
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from clients.client import LocalGPTClient, create_default_client
from .simple_jira_client import SimpleJiraClient
from .category_creator import CategoryCreator
from .task_classifier import TaskClassifier
from .csv_reporter import CSVReporter
from .models import JiraTask, Category, ClassificationResult, CategoryAnalysisResult

logger = logging.getLogger(__name__)


class JiraClassificationPipeline:
    """Основной пайплайн для классификации JIRA задач"""
    
    def __init__(self, llm_client: Optional[LocalGPTClient] = None):
        """
        Инициализация пайплайна
        
        Args:
            llm_client: Клиент LLM (если не указан, создается по умолчанию)
        """
        self.jira_client = SimpleJiraClient()
        self.llm_client = llm_client or create_default_client()
        self.category_creator = CategoryCreator(self.llm_client)
        self.task_classifier = TaskClassifier(self.llm_client)
        self.csv_reporter = CSVReporter()
        
        logger.info("Пайплайн классификации JIRA задач инициализирован")
    
    def run_full_pipeline(self, 
                         jql_query: str,
                         max_tasks: Optional[int] = None,
                         sample_size: int = 200,
                         save_intermediate: bool = True) -> Dict[str, str]:
        """
        Запустить полный пайплайн классификации
        
        Args:
            jql_query: JQL запрос для получения задач
            max_tasks: Максимальное количество задач (None = все)
            sample_size: Размер выборки для создания категорий
            save_intermediate: Сохранять промежуточные результаты
        
        Returns:
            Словарь с путями к созданным файлам
        """
        logger.info(f"Запуск полного пайплайна с JQL: {jql_query}")
        
        # Этап 1: Получение задач из JIRA
        logger.info("Этап 1: Получение задач из JIRA...")
        tasks = self._fetch_tasks_by_jql(jql_query, max_tasks)
        
        if save_intermediate:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            tasks_file = f"tasks_jql_{timestamp}.json"
            self.jira_client.save_tasks_to_json(tasks, tasks_file)
            logger.info(f"Задачи сохранены в файл: {tasks_file}")
        
        # Этап 2: Создание категорий
        logger.info("Этап 2: Создание категорий...")
        category_analysis = self._create_categories(tasks, sample_size)
        
        if save_intermediate:
            categories_file = f"categories_jql_{timestamp}.json"
            self._save_categories(category_analysis.categories, categories_file)
            logger.info(f"Категории сохранены в файл: {categories_file}")
        
        # Этап 3: Классификация задач
        logger.info("Этап 3: Классификация задач...")
        results = self._classify_tasks(tasks, category_analysis.categories)
        
        if save_intermediate:
            results_file = f"results_jql_{timestamp}.json"
            self._save_results(results, results_file)
            logger.info(f"Результаты классификации сохранены в файл: {results_file}")
        
        # Этап 4: Создание отчетов
        logger.info("Этап 4: Создание отчетов...")
        report_files = self._generate_reports(tasks, results, category_analysis.categories)
        
        logger.info("Пайплайн завершен успешно!")
        
        # Возвращаем информацию о результатах
        return {
            'tasks_count': len(tasks),
            'categories_count': len(category_analysis.categories),
            'avg_confidence': sum(r.confidence for r in results) / len(results),
            'reports': report_files,
            'recommendations': category_analysis.recommendations
        }
    
    def run_from_saved_tasks(self,
                           tasks_file: str,
                           sample_size: int = 200) -> Dict[str, str]:
        """
        Запустить пайплайн с загрузкой задач из файла
        
        Args:
            tasks_file: Путь к файлу с сохраненными задачами
            sample_size: Размер выборки для создания категорий
        
        Returns:
            Словарь с путями к созданным файлам
        """
        logger.info(f"Запуск пайплайна с загрузкой задач из файла: {tasks_file}")
        
        # Загружаем задачи
        tasks = self.jira_client.load_tasks_from_json(tasks_file)
        
        # Создаем категории
        category_analysis = self._create_categories(tasks, sample_size)
        
        # Классифицируем задачи
        results = self._classify_tasks(tasks, category_analysis.categories)
        
        # Создаем отчеты
        report_files = self._generate_reports(tasks, results, category_analysis.categories)
        
        return {
            'tasks_count': len(tasks),
            'categories_count': len(category_analysis.categories),
            'avg_confidence': sum(r.confidence for r in results) / len(results),
            'reports': report_files,
            'recommendations': category_analysis.recommendations
        }
    
    def run_classification_only(self,
                              tasks: List[JiraTask],
                              categories: List[Category]) -> List[ClassificationResult]:
        """
        Запустить только классификацию с готовыми категориями
        
        Args:
            tasks: Список задач
            categories: Готовые категории
        
        Returns:
            Результаты классификации
        """
        logger.info(f"Классификация {len(tasks)} задач по {len(categories)} категориям")
        return self._classify_tasks(tasks, categories)
    
    def _fetch_tasks_by_jql(self, 
                           jql_query: str,
                           max_tasks: Optional[int]) -> List[JiraTask]:
        """
        Получить задачи из JIRA по JQL запросу
        
        Args:
            jql_query: JQL запрос
            max_tasks: Максимальное количество задач
        
        Returns:
            Список задач
        """
        try:
            # Валидируем JQL запрос
            validation = self.jira_client.validate_jql(jql_query)
            if not validation['valid']:
                raise ValueError(f"Некорректный JQL запрос: {validation['message']}")
            
            tasks = self.jira_client.search_issues_by_jql(
                jql=jql_query,
                max_results=max_tasks
            )
            
            logger.info(f"Получено {len(tasks)} задач по JQL запросу")
            
            if not tasks:
                raise ValueError(f"Не найдено задач по JQL запросу: {jql_query}")
            
            return tasks
            
        except Exception as e:
            logger.error(f"Ошибка при получении задач: {e}")
            raise
    
    def _create_categories(self, 
                          tasks: List[JiraTask], 
                          sample_size: int) -> CategoryAnalysisResult:
        """
        Создать категории на основе анализа задач
        
        Args:
            tasks: Список задач
            sample_size: Размер выборки
        
        Returns:
            Результат анализа категорий
        """
        try:
            category_analysis = self.category_creator.create_categories(tasks, sample_size)
            
            logger.info(f"Создано {len(category_analysis.categories)} категорий")
            
            # Выводим рекомендации
            if category_analysis.recommendations:
                logger.info("Рекомендации по категориям:")
                for rec in category_analysis.recommendations:
                    logger.info(f"- {rec}")
            
            return category_analysis
            
        except Exception as e:
            logger.error(f"Ошибка при создании категорий: {e}")
            raise
    
    def _classify_tasks(self, 
                       tasks: List[JiraTask], 
                       categories: List[Category]) -> List[ClassificationResult]:
        """
        Классифицировать задачи
        
        Args:
            tasks: Список задач
            categories: Список категорий
        
        Returns:
            Результаты классификации
        """
        try:
            results = self.task_classifier.classify_tasks(tasks, categories)
            
            # Выводим статистику
            avg_confidence = sum(r.confidence for r in results) / len(results)
            low_confidence_count = len([r for r in results if r.confidence < 70])
            
            logger.info(f"Классификация завершена:")
            logger.info(f"- Средняя уверенность: {avg_confidence:.1f}%")
            logger.info(f"- Задач с низкой уверенностью: {low_confidence_count}")
            
            return results
            
        except Exception as e:
            logger.error(f"Ошибка при классификации задач: {e}")
            raise
    
    def _generate_reports(self, 
                         tasks: List[JiraTask],
                         results: List[ClassificationResult],
                         categories: List[Category]) -> Dict[str, str]:
        """
        Создать отчеты
        
        Args:
            tasks: Список задач
            results: Результаты классификации
            categories: Список категорий
        
        Returns:
            Пути к созданным отчетам
        """
        try:
            report_files = self.csv_reporter.generate_all_reports(tasks, results, categories)
            
            logger.info("Созданы отчеты:")
            for report_type, filepath in report_files.items():
                logger.info(f"- {report_type}: {filepath}")
            
            return report_files
            
        except Exception as e:
            logger.error(f"Ошибка при создании отчетов: {e}")
            raise
    
    def _save_categories(self, categories: List[Category], filename: str) -> None:
        """
        Сохранить категории в JSON файл
        
        Args:
            categories: Список категорий
            filename: Имя файла
        """
        categories_data = [cat.to_dict() for cat in categories]
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(categories_data, f, ensure_ascii=False, indent=2)
    
    def _save_results(self, results: List[ClassificationResult], filename: str) -> None:
        """
        Сохранить результаты классификации в JSON файл
        
        Args:
            results: Результаты классификации
            filename: Имя файла
        """
        results_data = []
        for result in results:
            result_dict = {
                'task_id': result.task_id,
                'category_scores': result.category_scores,
                'final_category': result.final_category,
                'confidence': result.confidence,
                'reasoning': result.reasoning,
                'alternative_categories': result.alternative_categories
            }
            results_data.append(result_dict)
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(results_data, f, ensure_ascii=False, indent=2)
    
    def load_categories(self, filename: str) -> List[Category]:
        """
        Загрузить категории из JSON файла
        
        Args:
            filename: Имя файла
        
        Returns:
            Список категорий
        """
        with open(filename, 'r', encoding='utf-8') as f:
            categories_data = json.load(f)
        
        categories = []
        for cat_dict in categories_data:
            category = Category(
                id=cat_dict['id'],
                name=cat_dict['name'],
                description=cat_dict['description'],
                keywords=cat_dict['keywords'],
                issue_types=cat_dict['issue_types'],
                examples=cat_dict['examples']
            )
            categories.append(category)
        
        return categories
