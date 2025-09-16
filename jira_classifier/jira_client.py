"""
Клиент для работы с JIRA с использованием библиотеки jira
"""

import json
from typing import List, Dict, Optional
from datetime import datetime
import logging
from jira import JIRA
from jira.exceptions import JIRAError
from .models import JiraTask

logger = logging.getLogger(__name__)


class JiraClient:
    """Клиент для работы с JIRA API с использованием библиотеки jira"""
    
    def __init__(self, server_url: str, username: str, api_token: str, verify_ssl: bool = False):
        """
        Инициализация клиента
        
        Args:
            server_url: URL JIRA сервера (например, https://company.atlassian.net)
            username: Имя пользователя или email
            api_token: API токен (для Atlassian Cloud) или пароль
            verify_ssl: Проверять SSL сертификат (по умолчанию False для корпоративных серверов)
        """
        self.server_url = server_url.rstrip('/')
        self.username = username
        
        try:
            # Создаем подключение к JIRA
            # Пробуем разные типы аутентификации
            auth_methods = [
                ('basic_auth', (username, api_token)),  # API токен или пароль
                ('token_auth', api_token),  # Персональный токен доступа
            ]
            
            connection_error = None
            for auth_type, auth_data in auth_methods:
                try:
                    if auth_type == 'basic_auth':
                        self.jira = JIRA(
                            server=self.server_url,
                            basic_auth=auth_data,
                            options={
                                'verify': verify_ssl,
                                'check_update': False
                            }
                        )
                    elif auth_type == 'token_auth':
                        self.jira = JIRA(
                            server=self.server_url,
                            token_auth=auth_data,
                            options={
                                'verify': verify_ssl,
                                'check_update': False
                            }
                        )
                    
                    # Проверяем подключение
                    self._test_connection()
                    logger.info(f"Успешное подключение с методом аутентификации: {auth_type}")
                    break
                    
                except JIRAError as e:
                    connection_error = e
                    logger.warning(f"Ошибка аутентификации с методом {auth_type}: {e}")
                    continue
            else:
                # Если ни один метод не сработал
                raise connection_error or JIRAError("Не удалось подключиться ни одним методом аутентификации")
            
        except JIRAError as e:
            logger.error(f"Ошибка подключения к JIRA: {e}")
            raise ConnectionError(f"Не удалось подключиться к JIRA: {e}")
    
    def _test_connection(self) -> None:
        """Тестирование подключения к JIRA"""
        try:
            user = self.jira.current_user()
            logger.info(f"Подключение к JIRA успешно. Пользователь: {user}")
        except JIRAError as e:
            logger.error(f"Ошибка при тестировании подключения: {e}")
            raise ConnectionError(f"Не удалось подключиться к JIRA: {e}")
    
    def get_projects(self) -> List[Dict]:
        """
        Получить список проектов
        
        Returns:
            Список проектов с основной информацией
        """
        try:
            projects = self.jira.projects()
            projects_info = []
            
            for project in projects:
                project_info = {
                    'key': project.key,
                    'name': project.name,
                    'description': getattr(project, 'description', ''),
                    'lead': getattr(project.lead, 'displayName', '') if hasattr(project, 'lead') and project.lead else '',
                    'projectTypeKey': getattr(project, 'projectTypeKey', '')
                }
                projects_info.append(project_info)
            
            logger.info(f"Получено {len(projects_info)} проектов")
            return projects_info
            
        except JIRAError as e:
            logger.error(f"Ошибка при получении проектов: {e}")
            raise
    
    def search_issues_by_jql(self, jql: str, max_results: Optional[int] = None) -> List[JiraTask]:
        """
        Поиск задач по JQL запросу
        
        Args:
            jql: JQL запрос для поиска задач
            max_results: Максимальное количество результатов (None = все)
        
        Returns:
            Список найденных задач
        """
        logger.info(f"Выполняем JQL запрос: {jql}")
        
        try:
            # Определяем поля для загрузки
            fields = [
                'summary', 'description', 'issuetype', 'status', 'assignee', 
                'reporter', 'created', 'updated', 'resolutiondate', 
                'timetracking', 'labels', 'components', 'priority',
                'timespent', 'timeoriginalestimate', 'worklog'
            ]
            
            # Выполняем поиск с пагинацией
            tasks = []
            start_at = 0
            max_per_request = 100  # JIRA API ограничение
            
            while True:
                # Определяем размер текущего батча
                current_max = max_per_request
                if max_results:
                    remaining = max_results - len(tasks)
                    if remaining <= 0:
                        break
                    current_max = min(max_per_request, remaining)
                
                # Выполняем запрос
                issues = self.jira.search_issues(
                    jql_str=jql,
                    startAt=start_at,
                    maxResults=current_max,
                    fields=fields,
                    expand='changelog'
                )
                
                if not issues:
                    break
                
                # Конвертируем в наши объекты
                for issue in issues:
                    task = self._convert_issue_to_task(issue)
                    if task:
                        tasks.append(task)
                
                # Проверяем, нужно ли продолжать
                if len(issues) < current_max:
                    break
                
                start_at += current_max
                logger.info(f"Получено {len(tasks)} задач...")
            
            logger.info(f"Всего найдено {len(tasks)} задач по JQL запросу")
            return tasks
            
        except JIRAError as e:
            logger.error(f"Ошибка при выполнении JQL запроса: {e}")
            raise
    
    def get_project_issues(self, project_key: str, 
                          additional_jql: Optional[str] = None,
                          max_results: Optional[int] = None) -> List[JiraTask]:
        """
        Получить задачи проекта
        
        Args:
            project_key: Ключ проекта
            additional_jql: Дополнительные условия JQL
            max_results: Максимальное количество результатов
        
        Returns:
            Список задач проекта
        """
        # Формируем JQL запрос
        jql = f"project = {project_key}"
        if additional_jql:
            jql += f" AND ({additional_jql})"
        
        return self.search_issues_by_jql(jql, max_results)
    
    def _convert_issue_to_task(self, issue) -> Optional[JiraTask]:
        """
        Конвертировать JIRA Issue в JiraTask
        
        Args:
            issue: Объект Issue из библиотеки jira
        
        Returns:
            Объект JiraTask или None в случае ошибки
        """
        try:
            # Получаем основные поля
            fields = issue.fields
            
            # Парсим даты
            created = datetime.fromisoformat(fields.created.replace('Z', '+00:00'))
            updated = datetime.fromisoformat(fields.updated.replace('Z', '+00:00'))
            resolved = None
            if fields.resolutiondate:
                resolved = datetime.fromisoformat(fields.resolutiondate.replace('Z', '+00:00'))
            
            # Получаем информацию о времени
            time_spent = 0
            original_estimate = None
            
            # Пробуем получить время из разных источников
            if hasattr(fields, 'timespent') and fields.timespent:
                time_spent = fields.timespent
            elif hasattr(fields, 'timetracking') and fields.timetracking:
                time_spent = getattr(fields.timetracking, 'timeSpentSeconds', 0) or 0
                original_estimate = getattr(fields.timetracking, 'originalEstimateSeconds', None)
            
            if hasattr(fields, 'timeoriginalestimate') and fields.timeoriginalestimate:
                original_estimate = fields.timeoriginalestimate
            
            # Получаем метки и компоненты
            labels = getattr(fields, 'labels', []) or []
            components = []
            if hasattr(fields, 'components') and fields.components:
                components = [comp.name for comp in fields.components]
            
            # Создаем объект задачи
            task = JiraTask(
                key=issue.key,
                title=fields.summary or '',
                description=fields.description or '',
                issue_type=fields.issuetype.name if fields.issuetype else 'Unknown',
                status=fields.status.name if fields.status else 'Unknown',
                assignee=fields.assignee.displayName if fields.assignee else None,
                reporter=fields.reporter.displayName if fields.reporter else 'Unknown',
                created=created,
                updated=updated,
                resolved=resolved,
                time_spent=time_spent,
                original_estimate=original_estimate,
                labels=labels,
                components=components,
                priority=fields.priority.name if fields.priority else 'Unknown'
            )
            
            return task
            
        except Exception as e:
            logger.warning(f"Ошибка при конвертации задачи {issue.key}: {e}")
            return None
    
    def get_issue_types(self, project_key: Optional[str] = None) -> List[Dict]:
        """
        Получить типы задач
        
        Args:
            project_key: Ключ проекта (если указан, вернет типы для конкретного проекта)
        
        Returns:
            Список типов задач
        """
        try:
            if project_key:
                project = self.jira.project(project_key)
                issue_types = project.issueTypes
            else:
                issue_types = self.jira.issue_types()
            
            types_info = []
            for issue_type in issue_types:
                type_info = {
                    'id': issue_type.id,
                    'name': issue_type.name,
                    'description': getattr(issue_type, 'description', ''),
                    'subtask': getattr(issue_type, 'subtask', False)
                }
                types_info.append(type_info)
            
            return types_info
            
        except JIRAError as e:
            logger.error(f"Ошибка при получении типов задач: {e}")
            raise
    
    def validate_jql(self, jql: str) -> Dict:
        """
        Проверить корректность JQL запроса
        
        Args:
            jql: JQL запрос для проверки
        
        Returns:
            Словарь с результатами валидации
        """
        try:
            # Выполняем тестовый запрос с ограничением в 1 результат
            self.jira.search_issues(jql_str=jql, maxResults=1)
            
            return {
                'valid': True,
                'message': 'JQL запрос корректен'
            }
            
        except JIRAError as e:
            return {
                'valid': False,
                'message': f'Ошибка в JQL запросе: {str(e)}'
            }
    
    def save_tasks_to_json(self, tasks: List[JiraTask], filename: str) -> None:
        """
        Сохранить задачи в JSON файл
        
        Args:
            tasks: Список задач
            filename: Имя файла
        """
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
                'created': task.created.isoformat(),
                'updated': task.updated.isoformat(),
                'resolved': task.resolved.isoformat() if task.resolved else None,
                'time_spent': task.time_spent,
                'original_estimate': task.original_estimate,
                'labels': task.labels,
                'components': task.components,
                'priority': task.priority
            }
            tasks_data.append(task_dict)
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(tasks_data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Сохранено {len(tasks)} задач в файл {filename}")
    
    def load_tasks_from_json(self, filename: str) -> List[JiraTask]:
        """
        Загрузить задачи из JSON файла
        
        Args:
            filename: Имя файла
        
        Returns:
            Список задач
        """
        with open(filename, 'r', encoding='utf-8') as f:
            tasks_data = json.load(f)
        
        tasks = []
        for task_dict in tasks_data:
            task = JiraTask(
                key=task_dict['key'],
                title=task_dict['title'],
                description=task_dict['description'],
                issue_type=task_dict['issue_type'],
                status=task_dict['status'],
                assignee=task_dict['assignee'],
                reporter=task_dict['reporter'],
                created=datetime.fromisoformat(task_dict['created']),
                updated=datetime.fromisoformat(task_dict['updated']),
                resolved=datetime.fromisoformat(task_dict['resolved']) if task_dict['resolved'] else None,
                time_spent=task_dict['time_spent'],
                original_estimate=task_dict['original_estimate'],
                labels=task_dict['labels'],
                components=task_dict['components'],
                priority=task_dict['priority']
            )
            tasks.append(task)
        
        logger.info(f"Загружено {len(tasks)} задач из файла {filename}")
        return tasks
    
    def get_jql_suggestions(self, project_key: Optional[str] = None) -> Dict[str, List[str]]:
        """
        Получить подсказки для составления JQL запросов
        
        Args:
            project_key: Ключ проекта для получения специфичных значений
        
        Returns:
            Словарь с подсказками для JQL
        """
        suggestions = {
            'examples': [
                f'project = {project_key}' if project_key else 'project = YOUR_PROJECT',
                f'project = {project_key} AND status != Closed' if project_key else 'project = YOUR_PROJECT AND status != Closed',
                f'project = {project_key} AND assignee = currentUser()' if project_key else 'project = YOUR_PROJECT AND assignee = currentUser()',
                f'project = {project_key} AND created >= -30d' if project_key else 'project = YOUR_PROJECT AND created >= -30d',
                f'project = {project_key} AND issuetype in (Bug, Task)' if project_key else 'project = YOUR_PROJECT AND issuetype in (Bug, Task)',
            ],
            'fields': [
                'project', 'status', 'assignee', 'reporter', 'issuetype',
                'priority', 'created', 'updated', 'resolved', 'labels',
                'component', 'fixVersion', 'affectedVersion'
            ],
            'operators': [
                '=', '!=', '>', '<', '>=', '<=', '~', '!~',
                'IN', 'NOT IN', 'IS', 'IS NOT'
            ],
            'functions': [
                'currentUser()', 'now()', 'startOfDay()', 'endOfDay()',
                'startOfWeek()', 'endOfWeek()', 'startOfMonth()', 'endOfMonth()'
            ]
        }
        
        try:
            if project_key:
                # Получаем статусы для проекта
                statuses = self.jira.statuses()
                suggestions['statuses'] = [status.name for status in statuses]
                
                # Получаем типы задач для проекта
                issue_types = self.get_issue_types(project_key)
                suggestions['issue_types'] = [it['name'] for it in issue_types]
                
        except JIRAError as e:
            logger.warning(f"Не удалось получить дополнительные подсказки: {e}")
        
        return suggestions