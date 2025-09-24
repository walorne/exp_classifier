"""
Модуль для работы с конфигурацией приложения
"""

import os
from typing import Optional, Dict, Any
from dotenv import load_dotenv
import logging

logger = logging.getLogger(__name__)


class Config:
    """Класс для управления конфигурацией приложения"""
    
    def __init__(self, env_file: str = '.env'):
        """
        Инициализация конфигурации
        
        Args:
            env_file: Путь к .env файлу
        """
        self.env_file = env_file
        self._load_env()
        self._jira_config = self._load_jira_config()
        self._defaults = self._load_defaults()
    
    def _load_env(self) -> None:
        """Загрузить переменные окружения из .env файла"""
        if os.path.exists(self.env_file):
            load_dotenv(self.env_file)
            logger.info(f"Загружены настройки из {self.env_file}")
        else:
            logger.warning(f"Файл {self.env_file} не найден. Используются переменные окружения.")
    
    def _load_jira_config(self) -> Dict[str, Any]:
        """Загрузить конфигурацию JIRA"""
        return {
            # Старые настройки (для совместимости)
            'server': os.getenv('JIRA_SERVER'),
            'username': os.getenv('JIRA_USERNAME'),
            'api_token': os.getenv('JIRA_API_TOKEN'),
            'verify_ssl': os.getenv('JIRA_VERIFY_SSL', 'false').lower() == 'true',
            
            # Новые упрощенные настройки
            'url': os.getenv('JIRA_URL'),
            'token': os.getenv('JIRA_TOKEN'),
            'cert_path': os.getenv('JIRA_CERT_PATH')
        }
    
    def _load_defaults(self) -> Dict[str, Any]:
        """Загрузить значения по умолчанию"""
        return {
            'max_tasks': int(os.getenv('DEFAULT_MAX_TASKS', '1000')),
            'sample_size': int(os.getenv('DEFAULT_SAMPLE_SIZE', '200')),
            'save_intermediate': os.getenv('DEFAULT_SAVE_INTERMEDIATE', 'true').lower() == 'true',
            'jql_query': os.getenv('DEFAULT_JQL_QUERY', '')
        }
    
    @property
    def jira_server(self) -> Optional[str]:
        """URL JIRA сервера"""
        return self._jira_config['server']
    
    @property
    def jira_username(self) -> Optional[str]:
        """Имя пользователя JIRA"""
        return self._jira_config['username']
    
    @property
    def jira_api_token(self) -> Optional[str]:
        """API токен JIRA"""
        return self._jira_config['api_token']
    
    @property
    def jira_verify_ssl(self) -> bool:
        """Проверять SSL сертификат JIRA"""
        return self._jira_config['verify_ssl']
    
    # Новые упрощенные свойства
    @property
    def jira_url(self) -> Optional[str]:
        """URL JIRA сервера (новый формат)"""
        return self._jira_config['url']
    
    @property
    def jira_token(self) -> Optional[str]:
        """Токен JIRA (новый формат)"""
        return self._jira_config['token']
    
    @property
    def jira_cert_path(self) -> Optional[str]:
        """Путь к сертификату JIRA"""
        return self._jira_config['cert_path']
    
    @property
    def default_max_tasks(self) -> int:
        """Максимальное количество задач по умолчанию"""
        return self._defaults['max_tasks']
    
    @property
    def default_sample_size(self) -> int:
        """Размер выборки по умолчанию"""
        return self._defaults['sample_size']
    
    @property
    def default_save_intermediate(self) -> bool:
        """Сохранять промежуточные файлы по умолчанию"""
        return self._defaults['save_intermediate']
    
    @property
    def default_jql_query(self) -> str:
        """JQL запрос по умолчанию"""
        return self._defaults['jql_query']
    
    def has_jira_config(self) -> bool:
        """Проверить, есть ли полная конфигурация JIRA"""
        # Проверяем новый упрощенный формат
        if self.jira_url and self.jira_token:
            return True
        
        # Проверяем старый формат (для совместимости)
        return all([
            self.jira_server,
            self.jira_username,
            self.jira_api_token
        ])
    
    def get_missing_jira_config(self) -> list[str]:
        """Получить список недостающих параметров JIRA"""
        missing = []
        if not self.jira_server:
            missing.append('JIRA_SERVER')
        if not self.jira_username:
            missing.append('JIRA_USERNAME')
        if not self.jira_api_token:
            missing.append('JIRA_API_TOKEN')
        return missing
    
    def validate_jira_config(self) -> tuple[bool, str]:
        """
        Валидировать конфигурацию JIRA
        
        Returns:
            Кортеж (валидна, сообщение об ошибке)
        """
        if self.has_jira_config():
            return True, "Конфигурация JIRA корректна"
        
        missing = self.get_missing_jira_config()
        error_msg = f"Отсутствуют обязательные параметры JIRA: {', '.join(missing)}"
        return False, error_msg
    
    def get_jira_config_dict(self) -> Dict[str, str]:
        """
        Получить конфигурацию JIRA в виде словаря
        
        Returns:
            Словарь с параметрами подключения к JIRA
        
        Raises:
            ValueError: Если конфигурация неполная
        """
        is_valid, error_msg = self.validate_jira_config()
        if not is_valid:
            raise ValueError(error_msg)
        
        return {
            'server': self.jira_server,
            'username': self.jira_username,
            'api_token': self.jira_api_token
        }
    
    def print_config_status(self) -> None:
        """Вывести статус конфигурации"""
        print("\n" + "="*50)
        print("СТАТУС КОНФИГУРАЦИИ")
        print("="*50)
        
        # JIRA конфигурация
        print("\n🔧 JIRA настройки:")
        
        # Новый упрощенный формат
        if self.jira_url and self.jira_token:
            print("   📋 Формат: упрощенный (JIRA_URL + JIRA_TOKEN)")
            print(f"   ✅ URL: {self.jira_url}")
            print(f"   ✅ Токен: {'*' * 10}...{self.jira_token[-4:]}")
            if self.jira_cert_path:
                print(f"   ✅ Сертификат: {self.jira_cert_path}")
            else:
                print("   ⚠️  Сертификат: не указан (SSL проверка отключена)")
        
        # Старый формат (для совместимости)
        elif self.jira_server or self.jira_username or self.jira_api_token:
            print("   📋 Формат: классический (JIRA_SERVER + JIRA_USERNAME + JIRA_API_TOKEN)")
            if self.jira_server:
                print(f"   ✅ Сервер: {self.jira_server}")
            else:
                print("   ❌ Сервер: не указан (JIRA_SERVER)")
            
            if self.jira_username:
                print(f"   ✅ Пользователь: {self.jira_username}")
            else:
                print("   ❌ Пользователь: не указан (JIRA_USERNAME)")
            
            if self.jira_api_token:
                print(f"   ✅ API токен: {'*' * 10}...{self.jira_api_token[-4:]}")
            else:
                print("   ❌ API токен: не указан (JIRA_API_TOKEN)")
        
        else:
            print("   ❌ Настройки JIRA не найдены")
        
        # Значения по умолчанию
        print(f"\n⚙️  Настройки по умолчанию:")
        print(f"   📊 Максимум задач: {self.default_max_tasks}")
        print(f"   🎯 Размер выборки: {self.default_sample_size}")
        print(f"   💾 Сохранять файлы: {'Да' if self.default_save_intermediate else 'Нет'}")
        print(f"   🔒 Проверка SSL: {'Да' if self.jira_verify_ssl else 'Нет'}")
        if self.default_jql_query:
            print(f"   🔍 JQL запрос: {self.default_jql_query}")
        else:
            print(f"   🔍 JQL запрос: не указан")
        
        # Общий статус
        is_valid, error_msg = self.validate_jira_config()
        if is_valid:
            print(f"\n✅ Конфигурация готова к использованию")
        else:
            print(f"\n❌ {error_msg}")
            print(f"\n💡 Для настройки:")
            print(f"   1. Скопируйте env.example как .env")
            print(f"   2. Заполните необходимые параметры")
            print(f"   3. Запустите скрипт снова")
    
    def create_env_template(self, filename: str = '.env') -> None:
        """
        Создать шаблон .env файла
        
        Args:
            filename: Имя файла для создания
        """
        template = """# JIRA Configuration
# Настройки подключения к JIRA

# URL вашего JIRA сервера (без слэша в конце)
# === УПРОЩЕННЫЙ ФОРМАТ (рекомендуется) ===
# URL вашего JIRA сервера
JIRA_URL=https://your-company.atlassian.net

# Токен для аутентификации (Personal Access Token или API Token)
JIRA_TOKEN=your_token_here

# Путь к сертификату (опционально, для корпоративных серверов)
JIRA_CERT_PATH=/path/to/certificate.crt

# === КЛАССИЧЕСКИЙ ФОРМАТ (для совместимости) ===
# JIRA_SERVER=https://your-company.atlassian.net
# JIRA_USERNAME=your-email@company.com
# JIRA_API_TOKEN=your_api_token_here

# Дополнительные настройки (опционально)
DEFAULT_MAX_TASKS=1000
DEFAULT_SAMPLE_SIZE=200
DEFAULT_SAVE_INTERMEDIATE=true

# JQL запрос по умолчанию (если не указан в аргументах)
# Примеры:
# DEFAULT_JQL_QUERY=project = MYPROJ
# DEFAULT_JQL_QUERY=project = MYPROJ AND status != Closed
DEFAULT_JQL_QUERY=

# Проверка SSL сертификата (false для корпоративных серверов с самоподписанными сертификатами)
JIRA_VERIFY_SSL=false
"""
        
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(template)
            print(f"✅ Создан шаблон конфигурации: {filename}")
            print("📝 Отредактируйте файл и укажите ваши настройки JIRA")
        except Exception as e:
            print(f"❌ Ошибка при создании шаблона: {e}")


# Глобальный экземпляр конфигурации
config = Config()
