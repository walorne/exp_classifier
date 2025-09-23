"""
Главный файл для запуска классификации JIRA задач
"""

import argparse
import logging
import sys
import os
from typing import Optional
from jira_classifier.config import config

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('jira_classifier.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

from jira_classifier.pipeline import JiraClassificationPipeline


def main():
    """Главная функция"""
    parser = argparse.ArgumentParser(
        description="Классификация JIRA задач с помощью LLM",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:

1. Полный пайплайн с настройками из .env:
   python main_jira_classifier.py --jql "project = MYPROJ"

2. С ограничением количества задач:
   python main_jira_classifier.py --jql "project = MYPROJ" --max-tasks 500

3. Сложный JQL запрос:
   python main_jira_classifier.py --jql "project = MYPROJ AND status != Closed AND created >= -30d"

4. Переопределение настроек из .env:
   python main_jira_classifier.py --jql "project = MYPROJ" --server https://other-jira.com --username other@email.com --token other_token

4. Обработка сохраненных задач:
   python main_jira_classifier.py --tasks-file tasks_MYPROJ_20231201_120000.json

5. Только получение задач без классификации:
   python main_jira_classifier.py --jql "project = MYPROJ" --fetch-only

6. Получение подсказок для JQL:
   python main_jira_classifier.py --jql-help

7. Проверка конфигурации:
   python main_jira_classifier.py --config-status

8. Создание шаблона .env файла:
   python main_jira_classifier.py --create-env
        """
    )
    
    # Основные параметры
    parser.add_argument(
        "--jql", "-q",
        type=str,
        help="JQL запрос для получения задач (например, 'project = MYPROJ AND status != Closed')"
    )
    
    parser.add_argument(
        "--server", "-s",
        type=str,
        help="URL JIRA сервера (переопределяет JIRA_SERVER из .env)"
    )
    
    parser.add_argument(
        "--username", "-u",
        type=str,
        help="Имя пользователя или email (переопределяет JIRA_USERNAME из .env)"
    )
    
    parser.add_argument(
        "--token", "-t",
        type=str,
        help="API токен JIRA (переопределяет JIRA_API_TOKEN из .env)"
    )
    
    # Дополнительные параметры
    parser.add_argument(
        "--max-tasks",
        type=int,
        help="Максимальное количество задач для обработки"
    )
    
    parser.add_argument(
        "--jql-help",
        action="store_true",
        help="Показать подсказки для составления JQL запросов"
    )
    
    parser.add_argument(
        "--config-status",
        action="store_true",
        help="Показать статус конфигурации из .env файла"
    )
    
    parser.add_argument(
        "--create-env",
        action="store_true",
        help="Создать шаблон .env файла"
    )
    
    parser.add_argument(
        "--sample-size",
        type=int,
        default=200,
        help="Размер выборки для создания категорий (по умолчанию: 200)"
    )
    
    # Режимы работы
    parser.add_argument(
        "--tasks-file",
        type=str,
        help="Путь к файлу с сохраненными задачами (для обработки без обращения к JIRA)"
    )
    
    parser.add_argument(
        "--fetch-only",
        action="store_true",
        help="Только получить задачи из JIRA без классификации"
    )
    
    parser.add_argument(
        "--no-save-intermediate",
        action="store_true",
        help="Не сохранять промежуточные результаты"
    )
    
    args = parser.parse_args()
    
    try:
        # Специальные команды
        if args.config_status:
            config.print_config_status()
            return
            
        if args.create_env:
            config.create_env_template()
            return
            
        if args.jql_help:
            show_jql_help(args)
            return
        
        # Получаем настройки JIRA (из .env или аргументов командной строки)
        jira_server = args.server or config.jira_server
        jira_username = args.username or config.jira_username
        jira_token = args.token or config.jira_api_token
        jql_query = args.jql or config.default_jql_query
        
        # Проверяем аргументы
        if not args.tasks_file:
            # Проверяем конфигурацию JIRA
            if not config.has_jira_config():
                print("❌ Отсутствует конфигурация JIRA!")
                print("\n💡 Для настройки выполните одно из:")
                print("   1. python main_jira_classifier.py --create-env  (создать .env файл)")
                print("   2. python main_jira_classifier.py --config-status  (проверить настройки)")
                print("   3. Указать параметры в командной строке: --server, --username, --token")
                return
            
            # Проверяем JQL запрос
            if not jql_query:
                print("❌ Не указан JQL запрос!")
                print("\n💡 Укажите JQL запрос одним из способов:")
                print("   1. В аргументе: --jql \"project = MYPROJ\"")
                print("   2. В .env файле: DEFAULT_JQL_QUERY=project = MYPROJ")
                print("   3. Получить помощь: python main_jira_classifier.py --jql-help")
                return
        
        if args.tasks_file:
            # Режим обработки сохраненных задач
            logger.info("Запуск в режиме обработки сохраненных задач")
            run_from_saved_tasks(args.tasks_file, args.sample_size)
        else:
            # Режим работы с JIRA
            if args.fetch_only:
                logger.info("Запуск в режиме получения задач")
                fetch_tasks_only(args, jql_query)
            else:
                logger.info("Запуск полного пайплайна")
                run_full_pipeline(args, jql_query)
        
        logger.info("Программа завершена успешно!")
        
    except KeyboardInterrupt:
        logger.info("Программа прервана пользователем")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        sys.exit(1)


def run_full_pipeline(args, jql_query: str):
    """
    Запустить полный пайплайн классификации
    
    Args:
        args: Аргументы командной строки
        jql_query: JQL запрос (из аргументов или конфигурации)
    """
    # Получаем настройки JIRA
    jira_server = args.server or config.jira_server
    jira_username = args.username or config.jira_username
    jira_token = args.token or config.jira_api_token
    
    # Создаем пайплайн
    pipeline = JiraClassificationPipeline(
        jira_server=jira_server,
        jira_username=jira_username,
        jira_api_token=jira_token,
        jira_verify_ssl=config.jira_verify_ssl
    )
    
    # Запускаем пайплайн
    results = pipeline.run_full_pipeline(
        jql_query=jql_query,
        max_tasks=args.max_tasks,
        sample_size=args.sample_size,
        save_intermediate=not args.no_save_intermediate
    )
    
    # Выводим результаты
    print("\n" + "="*60)
    print("РЕЗУЛЬТАТЫ КЛАССИФИКАЦИИ")
    print("="*60)
    print(f"📊 Обработано задач: {results['tasks_count']}")
    print(f"🏷️  Создано категорий: {results['categories_count']}")
    print(f"🎯 Средняя уверенность: {results['avg_confidence']:.1f}%")
    
    print(f"\n📄 Созданные отчеты:")
    for report_type, filepath in results['reports'].items():
        print(f"   - {report_type}: {filepath}")
    
    if results.get('recommendations'):
        print(f"\n💡 Рекомендации:")
        for rec in results['recommendations']:
            print(f"   - {rec}")
    
    print("\n✅ Классификация завершена! Откройте CSV файлы в Excel для анализа результатов.")


def run_from_saved_tasks(tasks_file: str, sample_size: int):
    """
    Запустить пайплайн с загрузкой задач из файла
    
    Args:
        tasks_file: Путь к файлу с задачами
        sample_size: Размер выборки
    """
    if not os.path.exists(tasks_file):
        raise FileNotFoundError(f"Файл с задачами не найден: {tasks_file}")
    
    # Создаем пайплайн (без JIRA подключения)
    pipeline = JiraClassificationPipeline(
        jira_server="dummy",
        jira_username="dummy", 
        jira_api_token="dummy"
    )
    
    # Запускаем обработку
    results = pipeline.run_from_saved_tasks(tasks_file, sample_size)
    
    # Выводим результаты
    print("\n" + "="*60)
    print("РЕЗУЛЬТАТЫ КЛАССИФИКАЦИИ")
    print("="*60)
    print(f"📊 Обработано задач: {results['tasks_count']}")
    print(f"🏷️  Создано категорий: {results['categories_count']}")
    print(f"🎯 Средняя уверенность: {results['avg_confidence']:.1f}%")
    
    print(f"\n📄 Созданные отчеты:")
    for report_type, filepath in results['reports'].items():
        print(f"   - {report_type}: {filepath}")
    
    if results.get('recommendations'):
        print(f"\n💡 Рекомендации:")
        for rec in results['recommendations']:
            print(f"   - {rec}")


def fetch_tasks_only(args, jql_query: str):
    """
    Только получить задачи из JIRA без классификации
    
    Args:
        args: Аргументы командной строки
        jql_query: JQL запрос (из аргументов или конфигурации)
    """
    from jira_classifier.jira_client import JiraClient
    from datetime import datetime
    
    # Получаем настройки JIRA
    jira_server = args.server or config.jira_server
    jira_username = args.username or config.jira_username
    jira_token = args.token or config.jira_api_token
    
    # Создаем JIRA клиент
    jira_client = JiraClient(jira_server, jira_username, jira_token, config.jira_verify_ssl)
    
    # Валидируем JQL
    validation = jira_client.validate_jql(jql_query)
    if not validation['valid']:
        print(f"❌ Некорректный JQL запрос: {validation['message']}")
        return
    
    # Получаем задачи
    tasks = jira_client.search_issues_by_jql(
        jql=jql_query,
        max_results=args.max_tasks
    )
    
    # Сохраняем задачи
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"tasks_jql_{timestamp}.json"
    jira_client.save_tasks_to_json(tasks, filename)
    
    print(f"\n✅ Получено и сохранено {len(tasks)} задач в файл: {filename}")
    print(f"JQL запрос: {jql_query}")
    if args.jql:
        print("Источник JQL: аргумент командной строки")
    else:
        print("Источник JQL: конфигурация (.env)")
    print(f"Для классификации запустите:")
    print(f"python main_jira_classifier.py --tasks-file {filename}")


def show_jql_help(args):
    """
    Показать подсказки для составления JQL запросов
    
    Args:
        args: Аргументы командной строки
    """
    from jira_classifier.jira_client import JiraClient
    
    print("\n" + "="*60)
    print("ПОДСКАЗКИ ПО JQL ЗАПРОСАМ")
    print("="*60)
    
    # Получаем настройки JIRA
    jira_server = args.server or config.jira_server
    jira_username = args.username or config.jira_username
    jira_token = args.token or config.jira_api_token
    
    if all([jira_server, jira_username, jira_token]):
        try:
            # Создаем клиент и получаем специфичные подсказки
            jira_client = JiraClient(jira_server, jira_username, jira_token, config.jira_verify_ssl)
            suggestions = jira_client.get_jql_suggestions()
            
            print("\n📋 Примеры JQL запросов:")
            for example in suggestions['examples']:
                print(f"   {example}")
            
            if 'issue_types' in suggestions:
                print(f"\n🏷️  Доступные типы задач:")
                for issue_type in suggestions['issue_types'][:10]:  # Показываем первые 10
                    print(f"   {issue_type}")
            
            if 'statuses' in suggestions:
                print(f"\n📊 Доступные статусы:")
                for status in suggestions['statuses'][:10]:  # Показываем первые 10
                    print(f"   {status}")
                    
        except Exception as e:
            print(f"⚠️  Не удалось получить специфичные подсказки: {e}")
    
    print("\n🔍 Основные поля для JQL:")
    print("   project, status, assignee, reporter, issuetype, priority")
    print("   created, updated, resolved, labels, component")
    
    print("\n⚙️  Операторы:")
    print("   =, !=, >, <, >=, <=, ~, !~, IN, NOT IN, IS, IS NOT")
    
    print("\n📅 Функции для дат:")
    print("   now(), startOfDay(), endOfDay(), startOfWeek(), endOfWeek()")
    print("   startOfMonth(), endOfMonth(), currentUser()")
    
    print("\n💡 Примеры полезных запросов:")
    print("   project = MYPROJ AND status != Closed")
    print("   project = MYPROJ AND created >= -30d")
    print("   project = MYPROJ AND assignee = currentUser()")
    print("   project = MYPROJ AND issuetype in (Bug, Task)")
    print("   project = MYPROJ AND updated >= startOfWeek()")
    
    print(f"\n📖 Подробная документация: https://support.atlassian.com/jira-service-management/docs/use-advanced-search-with-jira-query-language-jql/")


if __name__ == "__main__":
    main()
