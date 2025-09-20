import os
import platform

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
    "db_volume",
    "redis_volume",
    "logs",
}

# Файлы, которые нужно исключить по имени
EXCLUDE_FILES = {
    os.path.basename(__file__),
    "all_code.txt",
    "requirements.lock",
    "pytest-logs.txt",
    ".DS_Store",
    "package-lock.json",  # Часто слишком большой и не нужен для анализа
    "yarn.lock",
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
    ".js",  # Добавим JS для frontend
    ".jsx",
    ".ts",
    ".tsx",
    ".vue",
    ".css",
}

# Имена файлов, которые нужно включить, даже если их расширение не в списке
INCLUDE_FILENAMES = {
    "Dockerfile",
    ".env",
    ".gitignore",
    "requirements.txt",
    "requirements-dev.txt",
    "README",
    "package.json",  # Включаем package.json
}

### ИЗМЕНЕНИЕ 1: Добавляем "белый список" для папки frontend ###
# Указываем, какие конкретно файлы и папки из frontend нужно включить.
# Пути должны быть относительными и использовать '/' в качестве разделителя.
FRONTEND_WHITELIST_PATHS = {
    "frontend/src",  # Вся папка с исходным кодом
    "frontend/public/index.html",  # Главный HTML файл
    "frontend/package.json",
    "frontend/Dockerfile",
    "frontend/vite.config.js",  # Пример для Vite
    "frontend/vue.config.js",  # Пример для Vue CLI
}

# Ограничение на максимальный размер файла для включения (в байтах)
MAX_FILE_SIZE = 1 * 1024 * 1024

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


def generate_tree_structure_corrected(root_dir: str) -> str:
    """
    Генерирует корректное строковое представление структуры проекта.
    """
    print("Генерация структуры проекта...")
    abs_root_dir = os.path.abspath(root_dir)
    root_name = os.path.basename(abs_root_dir)
    tree_lines = [f"{root_name}/"]

    def recurse_tree(directory: str, prefix: str = ""):
        items = [
            item
            for item in os.listdir(directory)
            if item not in EXCLUDE_DIRS and item not in EXCLUDE_FILES
        ]

        dirs = sorted([d for d in items if os.path.isdir(os.path.join(directory, d))])
        files = sorted(
            [f for f in items if not os.path.isdir(os.path.join(directory, f))]
        )

        all_items = dirs + files

        for i, name in enumerate(all_items):
            connector = "└── " if i == len(all_items) - 1 else "├── "
            full_path = os.path.join(directory, name)

            tree_lines.append(
                f"{prefix}{connector}{name}{'/' if os.path.isdir(full_path) else ''}"
            )

            if os.path.isdir(full_path):
                new_prefix = prefix + ("    " if i == len(all_items) - 1 else "│   ")
                recurse_tree(full_path, new_prefix)

    recurse_tree(abs_root_dir)
    return "\n".join(tree_lines)


def collect_project_files_content() -> str:
    """
    Собирает содержимое всех указанных файлов в проекте.
    """
    print("Сбор содержимого файлов проекта...")
    all_content = []

    for root, dirs, files in os.walk(PROJECT_ROOT, topdown=True):
        dirs[:] = [d for d in sorted(dirs) if d not in EXCLUDE_DIRS]

        for file in sorted(files):
            file_path = os.path.join(root, file)
            relative_path = os.path.relpath(file_path, PROJECT_ROOT).replace("\\", "/")

            if file in EXCLUDE_FILES:
                continue

            ### ИЗМЕНЕНИЕ 2: Новая, более гибкая логика включения файлов ###
            def should_include(rel_path):
                # Сначала проверяем, не в папке ли frontend наш файл
                if rel_path.startswith("frontend/"):
                    # Если да, то он должен соответствовать белому списку
                    for whitelist_path in FRONTEND_WHITELIST_PATHS:
                        if rel_path.startswith(whitelist_path):
                            return True  # Нашли совпадение, включаем
                    return False  # Нет совпадений в белом списке, пропускаем

                # Если файл не в frontend, применяем общие правила
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
                print(
                    f"  (-) Пропускается (не удалось получить размер): {relative_path}"
                )
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
    project_structure = generate_tree_structure_corrected(PROJECT_ROOT)
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
