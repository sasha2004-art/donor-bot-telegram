import os
import subprocess

# --- НАСТРОЙКИ ---

# Имя выходного файла
OUTPUT_FILENAME = "all_code.txt"

# Корневая директория проекта ('.' означает текущую директорию)
PROJECT_ROOT = "."

# Папки, которые нужно исключить из сканирования
EXCLUDE_DIRS = {
    "__pycache__",  
    ".venv",         # Стандартное имя для виртуального окружения
    "venv",         
    ".git",         
    ".idea",    
    "node_modules",
    "migrations",    # Часто лучше исключить папки с миграциями БД
    ".vscode",       # Папка настроек VSCode
    "dist",          # Папка сборки
    "build",         # Еще одна папка сборки
    "txt",          # Папка для временных файлов
}

# Файлы, которые нужно исключить
EXCLUDE_FILES = {
    os.path.basename(__file__), # Исключаем сам этот скрипт
    "1.txt",                    # Исключаем выходной файл
    "requirements.lock",        # Часто генерируемые файлы зависимостей
}

# === НОВЫЕ НАСТРОЙКИ ДЛЯ ВЫБОРА ФАЙЛОВ ===

# Расширения файлов, которые нужно включить
INCLUDE_EXTENSIONS = {
    ".py",
    ".yml",
    ".yaml", # Часто используется наравне с .yml
    "html", # Включаем HTML-файлы
    ".md",  # Включаем Markdown-файлы
    ".txt", # Включаем текстовые файлы
    ".ini", # Включаем INI-файлы
}

# Имена файлов, которые нужно включить (даже без расширения или с нестандартным)
INCLUDE_FILENAMES = {
    "Dockerfile",
    ".env",
    ".gitignore",
    "requirements.txt",
}

# --- КОНЕЦ НАСТРОЕК ---

def get_project_structure():
    """
    Генерирует строковое представление структуры проекта с помощью утилиты tree.
    """
    print("Генерация структуры проекта...")
    try:
        # Формируем команду для tree, исключая указанные директории
        # -I - это флаг для исключения паттернов (папок/файлов)
        exclude_pattern = "|".join(EXCLUDE_DIRS)
        
        # Запускаем команду tree. Работает на Linux и macOS.
        # Для Windows, возможно, понадобится установить 'tree' (например, через Chocolatey)
        # или использовать команду без исключений: ['tree', PROJECT_ROOT, '/F']
        command = ['tree', PROJECT_ROOT, '-I', exclude_pattern]
        
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True,
            encoding='utf-8' # Явно указываем кодировку
        )
        return result.stdout
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        print(f" (!) Не удалось выполнить команду 'tree'. Убедитесь, что она установлена.")
        print(f" (!) Ошибка: {e}")
        return "Структура проекта не может быть сгенерирована, так как утилита 'tree' не найдена или вернула ошибку.\n"

def collect_project_files_content():
    """
    Собирает содержимое всех указанных файлов в проекте
    на основе настроек INCLUDE_EXTENSIONS и INCLUDE_FILENAMES.
    """
    print("Сбор содержимого файлов проекта...")
    all_content = []
    
    for root, dirs, files in os.walk(PROJECT_ROOT, topdown=True):
        # Исключаем нежелательные директории из обхода
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]

        for file in files:
            # Получаем расширение файла
            _, extension = os.path.splitext(file)

            # Проверяем, нужно ли включать этот файл
            should_include = (
                file in INCLUDE_FILENAMES or
                extension in INCLUDE_EXTENSIONS
            )
            
            # Пропускаем файл, если он не подходит или находится в списке исключений
            if not should_include or file in EXCLUDE_FILES:
                continue

            file_path = os.path.join(root, file)
            relative_path = os.path.relpath(file_path, PROJECT_ROOT)
            
            print(f"  -> Добавляется файл: {relative_path}")

            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Формируем блок для этого файла
                file_block = (
                    f"--- НАЧАЛО ФАЙЛА: {relative_path} ---\n\n"
                    f"{content}\n\n"
                    f"--- КОНЕЦ ФАЙЛА: {relative_path} ---\n\n"
                )
                all_content.append(file_block)
            except Exception as e:
                print(f" (!) Не удалось прочитать файл {relative_path}: {e}")
                all_content.append(f"--- НЕ УДАЛОСЬ ПРОЧИТАТЬ ФАЙЛ: {relative_path} | Ошибка: {e} ---\n\n")

    return "".join(all_content)

def main():
    """
    Главная функция для выполнения всех шагов.
    """
    # Шаг 1: Получаем структуру проекта
    project_structure = get_project_structure()
    
    # Шаг 2: Получаем содержимое всех нужных файлов
    files_content = collect_project_files_content()
    
    # Шаг 3: Записываем всё в один файл
    print(f"Запись результатов в файл '{OUTPUT_FILENAME}'...")
    try:
        with open(OUTPUT_FILENAME, 'w', encoding='utf-8') as f:
            f.write("="*20 + " СТРУКТУРА ПРОЕКТА " + "="*20 + "\n\n")
            f.write(project_structure)
            f.write("\n\n" + "="*20 + " СОДЕРЖИМОЕ ФАЙЛОВ " + "="*20 + "\n\n")
            f.write(files_content)
        print(f"\nГотово! Вся информация сохранена в файле '{OUTPUT_FILENAME}'.")
    except IOError as e:
        print(f" (!) Произошла ошибка при записи в файл: {e}")

if __name__ == "__main__":
    main()