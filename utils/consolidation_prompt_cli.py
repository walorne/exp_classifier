#!/usr/bin/env python3
"""
CLI утилита для управления промптами консолидации категорий
Версия 0.3
"""

import sys
from prompts.prompt_manager import create_category_prompt_manager


def show_help():
    """Показывает справку по использованию"""
    print("""
Утилита управления промптами для консолидации категорий

КОМАНДЫ:
  list                     - Показать все доступные промпты
  active                   - Показать активный промпт
  set <prompt_name>        - Установить активный промпт
  show <prompt_name>       - Показать содержимое промпта
  help                     - Показать эту справку

ПРИМЕРЫ:
  python consolidation_prompt_cli.py list
  python consolidation_prompt_cli.py set technical_focus
  python consolidation_prompt_cli.py show detailed_v1
    """)


def list_prompts():
    """Показывает список всех доступных промптов"""
    try:
        manager = create_category_prompt_manager()
        prompts = manager.list_category_consolidation_prompts()
        config = manager.load_category_consolidation_config()
        active_prompt = config.get('active_prompt', 'basic_v1')
        
        print("\nДоступные промпты для консолидации категорий:\n")
        
        for prompt_name, info in prompts.items():
            status = "[АКТИВНЫЙ]" if prompt_name == active_prompt else ""
            print(f"  {prompt_name} {status}")
            print(f"    Название: {info['name']}")
            print(f"    Описание: {info['description']}")
            
            # Показываем параметры
            params = manager.get_category_consolidation_parameters(prompt_name)
            if params:
                print(f"    Параметры: {params}")
            print()
            
    except Exception as e:
        print(f"Ошибка: {e}")


def show_active():
    """Показывает активный промпт"""
    try:
        manager = create_category_prompt_manager()
        config = manager.load_category_consolidation_config()
        active_prompt = config.get('active_prompt', 'basic_v1')
        
        print(f"\nАктивный промпт: {active_prompt}")
        
        # Показываем детали активного промпта
        prompts = manager.list_category_consolidation_prompts()
        if active_prompt in prompts:
            info = prompts[active_prompt]
            print(f"Название: {info['name']}")
            print(f"Описание: {info['description']}")
            
            # Показываем параметры
            params = manager.get_category_consolidation_parameters(active_prompt)
            if params:
                print(f"Параметры: {params}")
        
    except Exception as e:
        print(f"Ошибка: {e}")


def set_active_prompt(prompt_name):
    """Устанавливает активный промпт"""
    try:
        manager = create_category_prompt_manager()
        manager.set_active_category_consolidation_prompt(prompt_name)
        
        print(f"Активный промпт изменен на: {prompt_name}")
        
    except Exception as e:
        print(f"Ошибка: {e}")


def show_prompt_content(prompt_name):
    """Показывает содержимое промпта"""
    try:
        manager = create_category_prompt_manager()
        content = manager.get_category_consolidation_prompt(prompt_name)
        
        print(f"\nСодержимое промпта '{prompt_name}':")
        print("=" * 60)
        print(content)
        print("=" * 60)
        
        # Показываем параметры
        params = manager.get_category_consolidation_parameters(prompt_name)
        if params:
            print(f"\nПараметры промпта: {params}")
        
    except Exception as e:
        print(f"Ошибка: {e}")


def main():
    """Главная функция CLI"""
    if len(sys.argv) < 2:
        show_help()
        return
    
    command = sys.argv[1].lower()
    
    if command == 'help':
        show_help()
    elif command == 'list':
        list_prompts()
    elif command == 'active':
        show_active()
    elif command == 'set':
        if len(sys.argv) < 3:
            print("Ошибка: Укажите название промпта")
            print("   Пример: python consolidation_prompt_cli.py set technical_focus")
            return
        set_active_prompt(sys.argv[2])
    elif command == 'show':
        if len(sys.argv) < 3:
            print("Ошибка: Укажите название промпта")
            print("   Пример: python consolidation_prompt_cli.py show detailed_v1")
            return
        show_prompt_content(sys.argv[2])
    else:
        print(f"Неизвестная команда: {command}")
        show_help()


if __name__ == "__main__":
    main()
