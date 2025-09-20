import os
import platform

# --- НАСТРОЙКИ ---

# Имя выходного файла
OUTPUT_FILENAME = "all_code.txt"

# Корневая директория проекта ('.' означает текущую директорию)
PROJECT_ROOT = "."

# Папки, которые нужно полностью исключить из сканирования
# os.walk будет избегать заходить в них, что значительно ускоряет работу
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
    "db_volume",
    "redis_volume",
    "logs",
    "media",  # Добавлено для примера
    "static/admin", # Добавлено для примера
    "mypy_cache",
    ".mypy_cache",
    ".pytest_cache",
}

# Файлы, которые нужно исключить по имени
EXCLUDE_FILES = {
    os.path.basename(__file__),
    "all_code.txt",
    "requirements.lock",
    "pytest-logs.txt",
    ".DS_Store",
    "package-lock.json",
    "yarn.lock",
    ".env",
    "env",
}

# Расширения файлов, которые нужно включить (для файлов вне frontend)
INCLUDE_EXTENSIONS = {
    ".py",
    ".yml",
    ".yaml",
    ".html",
    ".md",
    ".txt",
    ".ini",
    ".mako",
    ".egg-info",
    ".json",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".vue",
    ".css",
    ".sh",
}

# Имена файлов, которые нужно включить, даже если их расширение не в списке
INCLUDE_FILENAMES = {
    "Dockerfile",
    ".env",
    ".gitignore",
    "requirements.txt",
    "requirements-dev.txt",
    "README",
    "package.json",
}

# "Белый список" для папки frontend.
# Если файл находится в `frontend/`, он будет включен, только если
# его путь соответствует одному из этих шаблонов.
FRONTEND_WHITELIST_PATHS = {
    "frontend/src",
    "frontend/public/index.html",
    "frontend/package.json",
    "frontend/Dockerfile",
    "frontend/vite.config.js",
    "frontend/vue.config.js",
}

# Ограничение на максимальный размер файла для включения (в байтах)
MAX_FILE_SIZE = 1 * 1024 * 1024  # 1 MB

# --- КОНЕЦ НАСТРОЕК ---


def is_binary(filepath: str) -> bool:
    """
    Проверяет, является ли файл бинарным, ища нулевые байты в его начале.
    """
    try:
        with open(filepath, "rb") as f:
            chunk = f.read(1024)
            return b"\0" in chunk
    except IOError:
        return True


def generate_tree_structure_optimized(root_dir: str) -> str:
    """
    Оптимизированная функция для генерации структуры проекта с использованием os.walk.
    """
    print("Генерация структуры проекта...")
    abs_root_dir = os.path.abspath(root_dir)
    root_name = os.path.basename(abs_root_dir)
    tree_lines = [f"{root_name}/"]
    
    # Используем os.walk для эффективного обхода
    for root, dirs, files in os.walk(abs_root_dir, topdown=True):
        # Исключаем директории "на лету", чтобы os.walk в них не заходил
        dirs[:] = [d for d in sorted(dirs) if d not in EXCLUDE_DIRS]
        files = [f for f in sorted(files) if f not in EXCLUDE_FILES]
        
        level = root.replace(abs_root_dir, '').count(os.sep)
        indent = '│   ' * level
        
        # Объединяем и сортируем для корректного отображения
        items_to_process = dirs + files
        
        for i, name in enumerate(items_to_process):
            connector = "└── " if i == len(items_to_process) - 1 else "├── "
            path = os.path.join(root, name)
            
            # Добавляем слэш для директорий
            suffix = "/" if os.path.isdir(path) else ""
            tree_lines.append(f"{indent}{connector}{name}{suffix}")

    return "\n".join(tree_lines)


def collect_project_files_content() -> str:
    """
    Собирает содержимое всех указанных файлов в проекте.
    """
    print("Сбор содержимого файлов проекта...")
    all_content = []

    for root, dirs, files in os.walk(PROJECT_ROOT, topdown=True):
        # Исключаем директории, чтобы не тратить время на их обход
        dirs[:] = [d for d in sorted(dirs) if d not in EXCLUDE_DIRS]

        for file in sorted(files):
            if file in EXCLUDE_FILES:
                continue

            file_path = os.path.join(root, file)
            relative_path = os.path.relpath(file_path, PROJECT_ROOT).replace("\\", "/")

            def should_include(rel_path):
                # Проверка для файлов внутри frontend
                if rel_path.startswith("frontend/"):
                    for whitelist_path in FRONTEND_WHITELIST_PATHS:
                        if rel_path.startswith(whitelist_path):
                            return True
                    return False

                # Общие правила для всех остальных файлов
                _, extension = os.path.splitext(rel_path)
                if file in INCLUDE_FILENAMES:
                    return True
                if extension in INCLUDE_EXTENSIONS:
                    return True

                return False

            if not should_include(relative_path):
                continue

            try:
                if os.path.getsize(file_path) > MAX_FILE_SIZE:
                    print(f"  (-) Пропускается (слишком большой): {relative_path}")
                    continue
            except OSError:
                print(f"  (-) Пропускается (не удалось получить размер): {relative_path}")
                continue

            if is_binary(file_path):
                print(f"  (-) Пропускается (бинарный файл): {relative_path}")
                continue

            print(f"  (+) Добавляется файл: {relative_path}")

            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()

                file_block = (
                    f"--- НАЧАЛО ФАЙЛА: {relative_path} ---\n\n"
                    f"{content.strip()}\n\n"
                    f"--- КОНЕЦ ФАЙЛА: {relative_path} ---\n\n"
                )
                all_content.append(file_block)
            except Exception as e:
                print(f"  (!) Не удалось прочитать файл {relative_path}: {e}")
                all_content.append(
                    f"--- НЕ УДАЛОСЬ ПРОЧИТАТЬ ФАЙЛ: {relative_path} | Ошибка: {e} ---\n\n"
                )

    return "".join(all_content)


def main():
    """Главная функция для выполнения всех шагов."""
    # Вызываем оптимизированную функцию для генерации дерева
    project_structure = generate_tree_structure_optimized(PROJECT_ROOT)
    files_content = collect_project_files_content()

    print(f"\nЗапись результатов в файл '{OUTPUT_FILENAME}'...")
    try:
        with open(OUTPUT_FILENAME, "w", encoding="utf-8") as f:
            f.write("=" * 20 + " СТРУКТУРА ПРОЕКТА " + "=" * 20 + "\n\n")
            f.write(project_structure)
            f.write("\n\n" + "=" * 20 + " СОДЕРЖИМОЕ ФАЙЛОВ " + "=" * 20 + "\n\n")
            f.write(files_content)
        print(f"Готово! Вся информация сохранена в файле '{OUTPUT_FILENAME}'.")
    except IOError as e:
        print(f" (!) Произошла ошибка при записи в файл: {e}")


if __name__ == "__main__":
    main()