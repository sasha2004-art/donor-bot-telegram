import argparse
import subprocess
import sys


# --- Утилиты для цветного вывода ---
class Colors:
    """Класс для цветного вывода в терминале."""

    HEADER = "\033[95m"
    OKBLUE = "\033[94m"
    OKGREEN = "\033[92m"
    WARNING = "\033[93m"
    FAIL = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"


# --- Пути для проверки ---
PATHS_TO_CHECK = "bot/ tests/"

# --- Конфигурация проверок ---
CHECKS = [
    # (
    #     "1. Formatting (black)",
    #     f"docker-compose run --rm bot black --check {PATHS_TO_CHECK}",
    # ),
    # (
    #     "2. Import Sorting (isort)",
    #     f"docker-compose run --rm bot isort --check-only {PATHS_TO_CHECK}",
    # ),
    # (
    #     "3. Linting (flake8)",
    #     f"docker-compose run --rm bot flake8 {PATHS_TO_CHECK} --count --ignore=E501,W503 --show-source --statistics",
    # ),
    # (
    #     "4. Static Type Checking (mypy)",
    #     f"docker-compose run --rm bot mypy {PATHS_TO_CHECK}",
    # ),
    # (
    #     "5. Code Security (bandit)",
    #     "docker-compose run --rm bot bandit -c pyproject.toml -r bot/",
    # ),
    (
        "6. Unit Tests (pytest)",
        "docker-compose run --rm bot pytest",
    ),
]

# --- Команды для ИСПРАВЛЕНИЯ кода ---
FIXES = [
    (
        "1. Auto-formatting (black)",
        f"docker-compose run --rm bot black {PATHS_TO_CHECK}",
    ),
    (
        "2. Auto-sorting imports (isort)",
        f"docker-compose run --rm bot isort {PATHS_TO_CHECK}",
    ),
]


def run_command(title: str, command: str, check_mode=True) -> bool:
    """Запускает одну команду и возвращает True в случае успеха."""
    print(f"\n{Colors.HEADER}--- {title} ---{Colors.ENDC}")
    print(f"{Colors.OKBLUE}COMMAND: {command}{Colors.ENDC}")

    # Используем shell=True для удобства, но это безопасно, т.к. команды формируются внутри скрипта
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore",
        shell=True,
    )

    if check_mode and result.returncode != 0:
        print(f"{Colors.FAIL}❌ FAILED{Colors.ENDC}")
        print(result.stdout)
        print(result.stderr)
        return False
    else:
        status_color = Colors.OKGREEN if result.returncode == 0 else Colors.WARNING
        status_text = "PASSED" if result.returncode == 0 else "DONE (with issues)"

        print(f"{status_color}✅ {status_text}{Colors.ENDC}")
        # Показываем вывод для тестов и для команд, которые что-то исправляют
        if not check_mode or "pytest" in command or result.stdout:
            print(result.stdout)
        return True


def run_flow(title: str, commands: list, check_mode: bool) -> bool:
    """Запускает набор команд и возвращает True, если ВСЕ они прошли."""
    action_word = "Verifying" if check_mode else "Fixing"
    print(f"\n{Colors.BOLD}🚀 Starting: {action_word} {title}...{Colors.ENDC}")

    all_passed = True
    for cmd_title, command in commands:
        if not run_command(cmd_title, command, check_mode=check_mode):
            all_passed = False

    return all_passed


def main():
    parser = argparse.ArgumentParser(
        description="Run verification and fixing scripts for the Donor Bot project."
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Automatically fix formatting and import sorting issues.",
    )
    args = parser.parse_args()

    # Перед запуском проверок останавливаем любые запущенные контейнеры,
    # чтобы избежать конфликтов имен.
    print(
        f"\n{Colors.OKBLUE}INFO: Stopping existing containers to avoid conflicts...{Colors.ENDC}"
    )
    subprocess.run(["docker-compose", "down"], capture_output=True, shell=False)

    if args.fix:
        run_flow("Code Style", FIXES, check_mode=False)
        print(
            f"\n{Colors.OKGREEN}Fixing process completed. Please run verification again to check the results.{Colors.ENDC}"
        )
        sys.exit(0)

    # Запуск всех проверок
    overall_success = run_flow("Code Quality", CHECKS, check_mode=True)

    # После всех проверок снова останавливаем контейнеры
    subprocess.run(["docker-compose", "down"], capture_output=True, shell=False)

    if overall_success:
        print(
            f"\n{Colors.OKGREEN}{Colors.BOLD}🎉 All checks passed successfully!{Colors.ENDC}"
        )
        sys.exit(0)
    else:
        print(
            f"\n{Colors.FAIL}{Colors.BOLD}❗️ Some checks failed. Please fix the errors and try again.{Colors.ENDC}"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
