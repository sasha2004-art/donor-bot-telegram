from unittest.mock import Mock, patch
from bot.utils.scheduler import setup_scheduler


def test_setup_scheduler_adds_all_jobs():
    """
    Тест: Проверяет, что функция setup_scheduler добавляет правильное
    количество задач с ожидаемыми параметрами.
    """
    # 1. Подготовка: Мокаем AsyncIOScheduler и его метод add_job
    with patch("bot.utils.scheduler.AsyncIOScheduler") as mock_scheduler_class:
        # Создаем экземпляр мока, который будет возвращаться при вызове AsyncIOScheduler()
        mock_scheduler_instance = mock_scheduler_class.return_value
        mock_scheduler_instance.add_job = Mock()

        # Создаем моки для аргументов функции
        mock_bot = Mock()
        mock_session_pool = Mock()
        mock_storage = Mock()

        # 2. Выполнение: Вызываем тестируемую функцию
        scheduler = setup_scheduler(mock_bot, mock_session_pool, mock_storage, "")

        # 3. Проверка
        # Проверяем, что экземпляр планировщика был создан
        mock_scheduler_class.assert_called_once_with(timezone="Europe/Moscow")

        # Проверяем, что scheduler.start() был вызван (хотя в setup он не вызывается, но это хорошая практика)
        # В вашем коде start() вызывается снаружи, так что этот assert не нужен
        # mock_scheduler_instance.start.assert_called_once()

        # Проверяем, что было добавлено правильное количество задач
        # В вашем коде 9 вызовов add_job
        assert mock_scheduler_instance.add_job.call_count == 10

        # Проверяем параметры одной из ключевых задач (например, проверка истечения медотводов)
        found_waiver_job_call = False
        for call in mock_scheduler_instance.add_job.call_args_list:
            # call.args - позиционные аргументы, call.kwargs - именованные
            func_arg = call.args[0]
            if func_arg.__name__ == "check_waiver_expirations":
                found_waiver_job_call = True
                assert call.kwargs["trigger"] == "cron"
                assert call.kwargs["hour"] == 9
                assert call.kwargs["minute"] == 0
                break

        assert (
            found_waiver_job_call
        ), "Задача check_waiver_expirations не была добавлена в планировщик"

        # Аналогично можно проверить параметры для других важных задач
        found_feedback_job_call = False
        for call in mock_scheduler_instance.add_job.call_args_list:
            if call.args[0].__name__ == "send_post_donation_feedback":
                found_feedback_job_call = True
                assert call.kwargs["hour"] == 11
                break

        assert (
            found_feedback_job_call
        ), "Задача send_post_donation_feedback не была добавлена"
