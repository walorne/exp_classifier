# JIRA Task Classifier

Система автоматической классификации JIRA задач с помощью LLM (Large Language Model).

## Возможности

- 🔍 **Автоматическое создание категорий** на основе анализа содержимого задач
- 🤖 **LLM-классификация** с оценкой релевантности для каждой категории  
- 📊 **Детальные CSV отчеты** для анализа в Excel
- 🎯 **JQL запросы** - гибкий поиск задач с помощью Jira Query Language
- ⚡ **Пакетная обработка** для оптимизации производительности
- 💾 **Сохранение промежуточных результатов** для повторного использования

## Установка

1. Клонируйте репозиторий:
```bash
git clone <repository-url>
cd exp_survey
```

2. Установите зависимости:
```bash
pip install -r requirements.txt
```

3. Настройте JIRA подключение:
```bash
# Создайте .env файл из шаблона
python main_jira_classifier.py --create-env

# Отредактируйте .env файл и укажите ваши настройки JIRA:
# JIRA_SERVER=https://your-company.atlassian.net
# JIRA_USERNAME=your-email@company.com  
# JIRA_API_TOKEN=your_api_token_here
```

4. Настройте подключение к LLM в `clients/client.py`

5. Проверьте конфигурацию:
```bash
python main_jira_classifier.py --config-status
```

## Использование

### Основные команды

#### Полный пайплайн классификации

```bash
# Использование JQL из .env файла (DEFAULT_JQL_QUERY)
python main_jira_classifier.py

# Указание JQL в аргументе (переопределяет настройки из .env)
python main_jira_classifier.py --jql "project = MYPROJ"

# С ограничением количества задач
python main_jira_classifier.py --jql "project = MYPROJ" --max-tasks 500
```

#### Сложные JQL запросы
```bash
# Только незакрытые задачи за последний месяц
python main_jira_classifier.py \
    --jql "project = MYPROJ AND status != Closed AND created >= -30d"

# Задачи определенных типов
python main_jira_classifier.py \
    --jql "project = MYPROJ AND issuetype in (Bug, Task, Story)" \
    --max-tasks 500

# Переопределение настроек из .env
python main_jira_classifier.py \
    --jql "project = MYPROJ" \
    --server https://other-jira.com \
    --username other@email.com \
    --token other_token
```

### Дополнительные возможности

#### Управление конфигурацией
```bash
# Проверить статус конфигурации
python main_jira_classifier.py --config-status

# Создать шаблон .env файла
python main_jira_classifier.py --create-env

# Получить помощь по JQL
python main_jira_classifier.py --jql-help
```

#### Только получение задач без классификации
```bash
# Использование JQL из .env
python main_jira_classifier.py --fetch-only

# Указание JQL в аргументе
python main_jira_classifier.py --jql "project = MYPROJ" --fetch-only
```

#### Классификация сохраненных задач
```bash
python main_jira_classifier.py --tasks-file tasks_jql_20231201_120000.json
```

#### Демо с тестовыми данными
```bash
python demo_jira_classifier.py
```

## Примеры JQL запросов

### Базовые запросы
```jql
# Все задачи проекта
project = MYPROJ

# Незакрытые задачи
project = MYPROJ AND status != Closed

# Задачи назначенные на меня
project = MYPROJ AND assignee = currentUser()

# Задачи за последние 30 дней
project = MYPROJ AND created >= -30d
```

### Продвинутые запросы
```jql
# Баги высокого приоритета
project = MYPROJ AND issuetype = Bug AND priority = High

# Задачи с определенными метками
project = MYPROJ AND labels in (urgent, critical)

# Задачи обновленные на этой неделе
project = MYPROJ AND updated >= startOfWeek()

# Задачи без исполнителя
project = MYPROJ AND assignee is EMPTY
```

## Структура проекта

```
exp_survey/
├── jira_classifier/           # Основной модуль классификации
│   ├── __init__.py
│   ├── models.py             # Модели данных
│   ├── jira_client.py        # JIRA API клиент (использует библиотеку jira)
│   ├── category_creator.py   # Создание категорий через LLM
│   ├── task_classifier.py    # Классификация задач
│   ├── csv_reporter.py       # Генерация CSV отчетов
│   └── pipeline.py           # Основной пайплайн
├── clients/                  # LLM клиенты
│   ├── client.py
│   └── main.py
├── reports/                  # Сгенерированные отчеты
├── main_jira_classifier.py   # Главный файл запуска
├── demo_jira_classifier.py   # Демо с тестовыми данными
└── requirements.txt
```

## Выходные отчеты

Система создает три типа CSV отчетов:

### 1. Основной отчет классификации
- Детальная информация по каждой задаче
- Назначенная категория и уверенность
- Альтернативные категории
- Полная информация о задаче (заголовок, описание, тип, исполнитель и т.д.)

### 2. Сводный отчет
- Статистика по каждой категории
- Количество задач и трудозатраты
- Средние и медианные значения времени
- Основные типы задач в категории

### 3. Отчет по низкой уверенности
- Задачи, требующие ручной проверки
- Рекомендации по улучшению классификации
- Альтернативные варианты категорий

## Алгоритм работы

1. **Получение задач** из JIRA через JQL запрос
2. **Валидация JQL** - проверка корректности запроса
3. **Создание выборки** для анализа (по умолчанию 200 задач)
4. **LLM анализ** выборки для создания категорий (до 25 категорий)
5. **Классификация всех задач** с оценкой релевантности
6. **Обработка исключений** - создание дополнительных категорий при необходимости
7. **Генерация отчетов** в формате CSV для Excel

## Настройка

### Конфигурация через .env файл

Создайте `.env` файл в корневой папке проекта:

```bash
# Создание шаблона
python main_jira_classifier.py --create-env
```

Заполните необходимые параметры:

```env
# URL вашего JIRA сервера
JIRA_SERVER=https://your-company.atlassian.net

# Email для входа в JIRA
JIRA_USERNAME=your-email@company.com

# API Token для Atlassian Cloud
JIRA_API_TOKEN=your_api_token_here

# Дополнительные настройки (опционально)
DEFAULT_MAX_TASKS=1000
DEFAULT_SAMPLE_SIZE=200
DEFAULT_SAVE_INTERMEDIATE=true

# JQL запрос по умолчанию (если не указан в аргументах)
DEFAULT_JQL_QUERY=project = MYPROJ AND status != Closed
```

### JIRA подключение
- **Atlassian Cloud**: используйте API токен (рекомендуется)
- **Jira Server**: может потребоваться пароль вместо токена
- **Права доступа**: нужны права на чтение задач проекта

### Получение API токена
1. Зайдите в https://id.atlassian.com/manage-profile/security/api-tokens
2. Создайте новый токен с описанием "JIRA Task Classifier"
3. Скопируйте токен в файл `.env` как `JIRA_API_TOKEN`

### Проверка конфигурации
```bash
# Проверить все настройки
python main_jira_classifier.py --config-status

# Тест подключения к JIRA
python main_jira_classifier.py --jql-help
```

### LLM настройки
Настройте параметры LLM в `clients/client.py`:
- API endpoint
- Модель
- Параметры генерации

## JQL (Jira Query Language)

### Основные поля
- `project` - проект
- `status` - статус задачи
- `assignee` - исполнитель
- `reporter` - создатель
- `issuetype` - тип задачи
- `priority` - приоритет
- `created` - дата создания
- `updated` - дата обновления
- `resolved` - дата решения
- `labels` - метки
- `component` - компонент

### Операторы
- `=, !=` - равно, не равно
- `>, <, >=, <=` - сравнения
- `~, !~` - содержит, не содержит
- `IN, NOT IN` - в списке, не в списке
- `IS, IS NOT` - является, не является

### Функции
- `currentUser()` - текущий пользователь
- `now()` - текущая дата и время
- `startOfDay(), endOfDay()` - начало/конец дня
- `startOfWeek(), endOfWeek()` - начало/конец недели
- `startOfMonth(), endOfMonth()` - начало/конец месяца

## Примеры категорий

Система автоматически создает категории на основе содержимого задач, например:

- **API интеграция** - настройка и поддержка API
- **Управление доступами** - предоставление/блокировка доступа
- **Работа с ошибками** - исправление багов и ошибок
- **Автоматизация** - сокращение ручных задач
- **Регулярная работа** - планерки, ретро, обсуждения

## Требования

- Python 3.8+
- Доступ к JIRA API
- Настроенный LLM клиент
- Интернет соединение для API запросов

## Зависимости

- `jira>=3.5.0` - официальная библиотека для работы с JIRA API
- `requests>=2.28.0` - HTTP запросы
- `openai>=1.0.0` - работа с LLM API
- `python-dateutil>=2.8.0` - работа с датами
- `python-dotenv>=1.0.0` - загрузка переменных окружения из .env файла

## Логирование

Все операции логируются в файл `jira_classifier.log` и выводятся в консоль.

## Поддержка

При возникновении проблем проверьте:
1. **Конфигурацию**: `python main_jira_classifier.py --config-status`
2. **JIRA подключение**: `python main_jira_classifier.py --jql-help`
3. **Корректность JQL**: используйте простые запросы для тестирования
4. **Права доступа**: убедитесь, что у пользователя есть доступ к проекту
5. **Настройки LLM**: проверьте `clients/client.py`
6. **Логи**: смотрите файл `jira_classifier.log`

### Частые проблемы

**"Отсутствует конфигурация JIRA"**
```bash
python main_jira_classifier.py --create-env
# Отредактируйте .env файл
python main_jira_classifier.py --config-status
```

**"Некорректный JQL запрос"**
```bash
# Попробуйте простой запрос
python main_jira_classifier.py --jql "project = YOUR_PROJECT_KEY"
```

**"Ошибка подключения к JIRA"**
- Проверьте URL сервера (без слэша в конце)
- Убедитесь в правильности API токена
- Проверьте сетевое подключение

## Полезные ссылки

- [JQL документация](https://support.atlassian.com/jira-service-management/docs/use-advanced-search-with-jira-query-language-jql/)
- [JIRA API документация](https://developer.atlassian.com/cloud/jira/platform/rest/v3/)
- [Создание API токена](https://support.atlassian.com/atlassian-account/docs/manage-api-tokens-for-your-atlassian-account/)