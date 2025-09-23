#!/usr/bin/env python3
"""
CLI утилита для управления промптами системы анализа JIRA задач
Версия 0.3
"""

import sys
from prompts.prompt_manager import create_category_prompt_manager


def show_help():
    """Показывает справку по использованию"""
    print("""
🎯 Утилита управления промптами

КОМАНДЫ:
  list [type]                     - Показать все доступные промпты (generation|consolidation)
  active [type]                   - Показать активный промпт (generation|consolidation)
  set <type> <prompt_name>        - Установить активный промпт
  show <type> <prompt_name>       - Показать содержимое промпта
  help                            - Показать эту справку

ТИПЫ ПРОМПТОВ:
  generation     - Промпты для генерации категорий
  consolidation  - Промпты для консолидации категорий

ПРИМЕРЫ:
  python prompt_manager_cli.py list generation
  python prompt_manager_cli.py set generation technical_focus
  python prompt_manager_cli.py show consolidation basic_v1
  python prompt_manager_cli.py active consolidation
    """)


def list_prompts():
    """Показывает список всех доступных промптов"""
    try:
        manager = create_category_prompt_manager()
        prompts = manager.list_category_generation_prompts()
        config = manager.load_category_generation_config()
        active_prompt = config.get('active_prompt', 'basic_v1')
        
        print("\n📋 Доступные промпты для генерации категорий:\n")
        
        for prompt_name, info in prompts.items():
            status = "🎯 АКТИВНЫЙ" if prompt_name == active_prompt else ""
            print(f"  {prompt_name} {status}")
            print(f"    Название: {info['name']}")
            print(f"    Описание: {info['description']}")
            
            # Показываем параметры
            params = manager.get_category_generation_parameters(prompt_name)
            if params:
                print(f"    Параметры: {params}")
            print()
            
    except Exception as e:
        print(f"❌ Ошибка: {e}")


def show_active():
    """Показывает активный промпт"""
    try:
        manager = create_category_prompt_manager()
        config = manager.load_category_generation_config()
        active_prompt = config.get('active_prompt', 'basic_v1')
        prompts = manager.list_category_generation_prompts()
        
        if active_prompt in prompts:
            info = prompts[active_prompt]
            print(f"\n🎯 Активный промпт: {active_prompt}")
            print(f"Название: {info['name']}")
            print(f"Описание: {info['description']}")
            
            params = manager.get_category_generation_parameters(active_prompt)
            if params:
                print(f"Параметры: {params}")
        else:
            print(f"❌ Активный промпт '{active_prompt}' не найден!")
            
    except Exception as e:
        print(f"❌ Ошибка: {e}")


def set_active_prompt(prompt_name):
    """Устанавливает активный промпт"""
    try:
        manager = create_category_prompt_manager()
        manager.set_active_category_generation_prompt(prompt_name)
        
        # Показываем информацию о новом активном промпте
        prompts = manager.list_category_generation_prompts()
        if prompt_name in prompts:
            info = prompts[prompt_name]
            print(f"🎯 Новый активный промпт: {info['name']}")
            
    except Exception as e:
        print(f"❌ Ошибка: {e}")


def show_prompt_content(prompt_name):
    """Показывает содержимое промпта"""
    try:
        manager = create_category_prompt_manager()
        prompt_text = manager.get_category_generation_prompt(prompt_name)
        prompts = manager.list_category_generation_prompts()
        
        if prompt_name in prompts:
            info = prompts[prompt_name]
            print(f"\n📄 Промпт: {info['name']} ({prompt_name})")
            print(f"Описание: {info['description']}")
            
            params = manager.get_category_generation_parameters(prompt_name)
            if params:
                print(f"Параметры: {params}")
            
            print("\n" + "="*60)
            print("СОДЕРЖИМОЕ ПРОМПТА:")
            print("="*60)
            print(prompt_text)
            print("="*60)
        else:
            print(f"❌ Промпт '{prompt_name}' не найден!")
            
    except Exception as e:
        print(f"❌ Ошибка: {e}")


def main():
    """Главная функция CLI"""
    if len(sys.argv) < 2:
        show_help()
        return
    
    command = sys.argv[1].lower()
    
    if command == "help":
        show_help()
    elif command == "list":
        list_prompts()
    elif command == "active":
        show_active()
    elif command == "set":
        if len(sys.argv) < 3:
            print("❌ Укажите название промпта: python prompt_manager_cli.py set <prompt_name>")
            return
        prompt_name = sys.argv[2]
        set_active_prompt(prompt_name)
    elif command == "show":
        if len(sys.argv) < 3:
            print("❌ Укажите название промпта: python prompt_manager_cli.py show <prompt_name>")
            return
        prompt_name = sys.argv[2]
        show_prompt_content(prompt_name)
    else:
        print(f"❌ Неизвестная команда: {command}")
        show_help()


if __name__ == "__main__":
    main()
