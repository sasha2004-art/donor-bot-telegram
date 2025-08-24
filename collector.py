import os
import subprocess
import platform  # Импортируем для определения ОС

# --- НАСТРОЙКИ ---

# Имя выходного файла
OUTPUT_FILENAME = "all_code.txt"

# Корневая директория проекта ('.' означает текущую директорию)
PROJECT_ROOT = "."

# Папки, которые нужно полностью исключить из сканирования
EXCLUDE_DIRS = {
    "__pycache__",
    ".venv",
    "venv",
    ".git",
    ".idea",
    ".vscode",
    "node_modules",
    "dist",
    "build",
    "db_volume",      # Добавлено из вашего .gitignore
    "redis_volume",   # Добавлено из вашего docker-compose
    "logs",           # Часто бывают папки с логами
}

# Файлы, которые нужно исключить по имени
EXCLUDE_FILES = {
    os.path.basename(__file__),  # Исключаем сам этот скрипт
    "all_code.txt",
    "requirements.lock",
    "pytest-logs.txt", # Лог-файл из pytest.ini
    ".DS_Store",       # Системный файл macOS
}

# Расширения файлов, которые нужно включить
INCLUDE_EXTENSIONS = {
    ".py",
    ".yml",
    ".yaml",
    ".html",
    ".md",
    ".txt",
    ".ini",
    ".mako", # Добавлено для alembic
    ".egg-info", # Может быть полезно для отладки зависимостей
}

# Имена файлов, которые нужно включить, даже если их расширение не в списке
INCLUDE_FILENAMES = {
    "Dockerfile",
    ".env",
    ".gitignore",
    "requirements.txt",
    "requirements-dev.txt",
    "README", # Файл alembic/README без расширения
}

# НОВОЕ: Ограничение на максимальный размер файла для включения (в байтах)
# 1 МБ = 1 * 1024 * 1024. Это предотвратит включение больших логов или данных.
MAX_FILE_SIZE = 1 * 1024 * 1024

# --- КОНЕЦ НАСТРОЕК ---

def is_binary(filepath: str) -> bool:
    """
    Проверяет, является ли файл бинарным, ища нулевые байты в его начале.
    Это простой и довольно надежный способ отличить текстовые файлы от бинарных.
    """
    try:
        with open(filepath, 'rb') as f:
            # Читаем первые 1024 байта
            chunk = f.read(1024)
            # Если в этом куске есть нулевой байт, скорее всего, это бинарный файл
            return b'\0' in chunk
    except IOError:
        return True # Если не можем прочитать, считаем бинарным на всякий случай

def generate_tree_structure_pythonic(root_dir: str) -> str:
    """
    Генерирует строковое представление структуры проекта на чистом Python.
    Работает на любой ОС, не зависит от внешней команды 'tree'.
    """
    print("Генерация структуры проекта (Python-реализация)...")
    tree_lines = [f"{os.path.basename(root_dir)}/"]
    
    # os.walk рекурсивно обходит все директории
    for root, dirs, files in os.walk(root_dir, topdown=True):
        # Исключаем нежелательные директории прямо во время обхода
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        
        level = root.replace(root_dir, '').count(os.sep)
        indent = '│   ' * (level) + '├── '
        
        # Сортируем для консистентного вывода
        dirs.sort()
        files.sort()
        
        # Объединяем папки и файлы для корректного отображения последнего элемента
        items = dirs + files
        for i, item_name in enumerate(items):
            # Пропускаем исключенные файлы и папки
            if item_name in EXCLUDE_FILES or item_name in EXCLUDE_DIRS:
                continue

            # Определяем префикс для последнего элемента в директории
            if i == len(items) - 1:
                indent = '│   ' * (level) + '└── '

            path = os.path.join(root, item_name)
            if os.path.isdir(path):
                tree_lines.append(f"{indent}{item_name}/")
            else:
                tree_lines.append(f"{indent}{item_name}")

    return "\n".join(tree_lines)


def collect_project_files_content() -> str:
    """
    Собирает содержимое всех указанных файлов в проекте
    на основе настроек, с проверкой на бинарность и размер.
    """
    print("Сбор содержимого файлов проекта...")
    all_content = []
    
    for root, dirs, files in os.walk(PROJECT_ROOT, topdown=True):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]

        for file in sorted(files): # Сортируем для предсказуемого порядка
            file_path = os.path.join(root, file)
            relative_path = os.path.relpath(file_path, PROJECT_ROOT).replace('\\', '/')

            # 1. Проверка на явное исключение файла
            if file in EXCLUDE_FILES:
                continue

            # 2. Проверка на соответствие правилам включения
            _, extension = os.path.splitext(file)
            should_include = (
                file in INCLUDE_FILENAMES or
                extension in INCLUDE_EXTENSIONS
            )
            if not should_include:
                continue
            
            # 3. НОВОЕ: Проверка размера файла
            try:
                if os.path.getsize(file_path) > MAX_FILE_SIZE:
                    print(f"  (-) Пропускается (слишком большой): {relative_path}")
                    continue
            except OSError:
                print(f"  (-) Пропускается (не удалось получить размер): {relative_path}")
                continue
                
            # 4. НОВОЕ: Проверка на бинарность
            if is_binary(file_path):
                print(f"  (-) Пропускается (бинарный файл): {relative_path}")
                continue

            print(f"  (+) Добавляется файл: {relative_path}")

            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                
                file_block = (
                    f"--- НАЧАЛО ФАЙЛА: {relative_path} ---\n\n"
                    f"{content.strip()}\n\n"
                    f"--- КОНЕЦ ФАЙЛА: {relative_path} ---\n\n"
                )
                all_content.append(file_block)
            except Exception as e:
                print(f"  (!) Не удалось прочитать файл {relative_path}: {e}")
                all_content.append(f"--- НЕ УДАЛОСЬ ПРОЧИТАТЬ ФАЙЛ: {relative_path} | Ошибка: {e} ---\n\n")

    return "".join(all_content)

def main():
    """Главная функция для выполнения всех шагов."""
    # Шаг 1: Получаем структуру проекта
    project_structure = generate_tree_structure_pythonic(PROJECT_ROOT)
    
    # Шаг 2: Получаем содержимое всех нужных файлов
    files_content = collect_project_files_content()
    
    # Шаг 3: Записываем всё в один файл
    print(f"\nЗапись результатов в файл '{OUTPUT_FILENAME}'...")
    try:
        with open(OUTPUT_FILENAME, 'w', encoding='utf-8') as f:
            f.write("="*20 + " СТРУКТУРА ПРОЕКТА " + "="*20 + "\n\n")
            f.write(project_structure)
            f.write("\n\n" + "="*20 + " СОДЕРЖИМОЕ ФАЙЛОВ " + "="*20 + "\n\n")
            f.write(files_content)
        print(f"Готово! Вся информация сохранена в файле '{OUTPUT_FILENAME}'.")
    except IOError as e:
        print(f" (!) Произошла ошибка при записи в файл: {e}")

if __name__ == "__main__":
    main()