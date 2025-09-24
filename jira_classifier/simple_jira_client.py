"""
Упрощенный JIRA клиент для классификации задач
"""
import logging
import json
from typing import List, Dict, Optional
from datetime import datetime
from jira import JIRA
from jira_simple_client import get_jira_client
from .models import JiraTask

logger = logging.getLogger(__name__)


class SimpleJiraClient:
    """Упрощенный клиент для работы с JIRA через простую функцию get_jira_client()"""
    
    def __init__(self):
        """Инициализация через простую функцию"""
        try:
            self.jira = get_jira_client()
            logger.info("JIRA клиент успешно создан")
        except Exception as e:
            logger.error(f"Ошибка создания JIRA клиента: {e}")
            raise
    
    def search_issues_by_jql(self, jql: str, max_results: Optional[int] = None) -> List[JiraTask]:
        """
        Поиск задач по JQL запросу
        
        Args:
            jql: JQL запрос
            max_results: Максимальное количество результатов
            
        Returns:
            Список задач JiraTask
        """
        try:
            logger.info(f"Выполнение JQL запроса: {jql}")
            
            # Поля для получения
            fields = [
                'key', 'summary', 'description', 'issuetype', 'status', 
                'assignee', 'reporter', 'created', 'updated', 'resolved',
                'timetracking', 'labels', 'components'
            ]
            
            # Выполняем запрос
            issues = self.jira.search_issues(
                jql_str=jql,
                maxResults=max_results or 1000,
                fields=fields
            )
            
            # Преобразуем в JiraTask
            tasks = []
            for issue in issues:
                task = self._convert_issue_to_task(issue)
                tasks.append(task)
                
            logger.info(f"Найдено {len(tasks)} задач")
            return tasks
            
        except Exception as e:
            logger.error(f"Ошибка при выполнении JQL запроса: {e}")
            raise
    
    def validate_jql(self, jql: str) -> Dict[str, bool]:
        """
        Валидация JQL запроса
        
        Args:
            jql: JQL запрос для проверки
            
        Returns:
            Словарь с результатом валидации
        """
        try:
            # Простая валидация - пробуем выполнить запрос с лимитом 1
            self.jira.search_issues(jql_str=jql, maxResults=1)
            return {'valid': True, 'message': 'JQL запрос корректен'}
        except Exception as e:
            return {'valid': False, 'message': str(e)}
    
    def get_jql_suggestions(self) -> Dict[str, List[str]]:
        """
        Получить подсказки для JQL запросов
        
        Returns:
            Словарь с примерами запросов
        """
        return {
            'examples': [
                'project = MYPROJ',
                'project = MYPROJ AND status != Closed',
                'project = MYPROJ AND created >= -30d',
                'assignee = currentUser() AND status = "In Progress"',
                'project = MYPROJ AND issuetype = Bug',
                'project = MYPROJ AND priority = High'
            ]
        }
    
    def save_tasks_to_json(self, tasks: List[JiraTask], filename: str):
        """
        Сохранить задачи в JSON файл
        
        Args:
            tasks: Список задач для сохранения
            filename: Имя файла для сохранения
        """
        try:
            # Преобразуем в словари для сериализации
            tasks_data = []
            for task in tasks:
                task_dict = {
                    'key': task.key,
                    'title': task.title,
                    'description': task.description,
                    'issue_type': task.issue_type,
                    'status': task.status,
                    'assignee': task.assignee,
                    'reporter': task.reporter,
                    'created': task.created.isoformat() if task.created else None,
                    'updated': task.updated.isoformat() if task.updated else None,
                    'resolved': task.resolved.isoformat() if task.resolved else None,
                    'time_spent_seconds': task.time_spent_seconds,
                    'original_estimate_seconds': task.original_estimate_seconds,
                    'labels': task.labels,
                    'components': task.components
                }
                tasks_data.append(task_dict)
            
            # Сохраняем в файл
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(tasks_data, f, ensure_ascii=False, indent=2)
                
            logger.info(f"Сохранено {len(tasks)} задач в файл: {filename}")
            
        except Exception as e:
            logger.error(f"Ошибка при сохранении задач: {e}")
            raise
    
    def _convert_issue_to_task(self, issue) -> JiraTask:
        """
        Преобразовать JIRA Issue в JiraTask
        
        Args:
            issue: Объект JIRA Issue
            
        Returns:
            Объект JiraTask
        """
        try:
            # Безопасное извлечение данных
            def safe_get(obj, attr, default=None):
                try:
                    value = getattr(obj, attr, default)
                    return value if value is not None else default
                except:
                    return default
            
            def safe_get_field(fields, field_name, default=None):
                try:
                    value = getattr(fields, field_name, default)
                    return value if value is not None else default
                except:
                    return default
            
            def parse_datetime(date_str):
                try:
                    if date_str:
                        # JIRA возвращает datetime в формате ISO
                        return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                    return None
                except:
                    return None
            
            # Основные поля
            key = safe_get(issue, 'key', '')
            fields = safe_get(issue, 'fields')
            
            # Извлекаем данные из fields
            title = safe_get_field(fields, 'summary', '')
            description = safe_get_field(fields, 'description', '')
            
            # Тип задачи
            issuetype = safe_get_field(fields, 'issuetype')
            issue_type = safe_get(issuetype, 'name', '') if issuetype else ''
            
            # Статус
            status_obj = safe_get_field(fields, 'status')
            status = safe_get(status_obj, 'name', '') if status_obj else ''
            
            # Пользователи
            assignee_obj = safe_get_field(fields, 'assignee')
            assignee = safe_get(assignee_obj, 'displayName', '') if assignee_obj else None
            
            reporter_obj = safe_get_field(fields, 'reporter')
            reporter = safe_get(reporter_obj, 'displayName', '') if reporter_obj else None
            
            # Даты
            created = parse_datetime(safe_get_field(fields, 'created'))
            updated = parse_datetime(safe_get_field(fields, 'updated'))
            resolved = parse_datetime(safe_get_field(fields, 'resolved'))
            
            # Время работы
            timetracking = safe_get_field(fields, 'timetracking', {})
            time_spent_seconds = safe_get(timetracking, 'timeSpentSeconds', 0) or 0
            original_estimate_seconds = safe_get(timetracking, 'originalEstimateSeconds', 0) or 0
            
            # Метки
            labels = safe_get_field(fields, 'labels', []) or []
            
            # Компоненты
            components_list = safe_get_field(fields, 'components', []) or []
            components = [safe_get(comp, 'name', '') for comp in components_list]
            
            return JiraTask(
                key=key,
                title=title,
                description=description,
                issue_type=issue_type,
                status=status,
                assignee=assignee,
                reporter=reporter,
                created=created,
                updated=updated,
                resolved=resolved,
                time_spent_seconds=time_spent_seconds,
                original_estimate_seconds=original_estimate_seconds,
                labels=labels,
                components=components
            )
            
        except Exception as e:
            logger.error(f"Ошибка при конвертации задачи {issue.key}: {e}")
            # Возвращаем минимальную задачу
            return JiraTask(
                key=safe_get(issue, 'key', 'UNKNOWN'),
                title=f"Ошибка загрузки: {e}",
                description="",
                issue_type="Unknown",
                status="Unknown"
            )
