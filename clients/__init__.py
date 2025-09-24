"""
Пакет клиентов для подключения к различным системам и сервисам
"""

from .ai_client import LocalGPTClient, create_default_client

__all__ = [
    'LocalGPTClient',
    'create_default_client'
]
