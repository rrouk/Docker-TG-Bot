import os
import asyncio
import docker
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from dotenv import load_dotenv
import datetime # Импортируем модуль datetime для явного обращения к классу
from datetime import timezone # timezone оставил для удобства

load_dotenv()

class DockerBot:
    def __init__(self):
        self.bot_token = os.getenv('BOT_TOKEN')
        # Опционально: ограничить доступ определенным пользователям
        self.allowed_users = [int(user_id) for user_id in os.getenv('ALLOWED_USERS', '').split(',') if user_id]
        # Настройка Docker клиента для работы с socket
        try:
            # Проверяем доступность socket
            if not os.path.exists('/var/run/docker.sock'):
                raise Exception("Docker socket не найден: /var/run/docker.sock")

            # Используем прямой путь к socket
            self.docker_client = docker.DockerClient(base_url='unix:///var/run/docker.sock')
            # Проверяем подключение к Docker
            self.docker_client.ping()
            print("Docker подключение успешно установлено")
        except Exception as e:
            print(f"Ошибка подключения к Docker: {e}")
            print("Убедитесь, что Docker socket смонтирован в контейнер")
            raise


    def _format_uptime(self, started_at_str):
        """
        Calculates and formats the uptime from the ISO 8601 string returned by Docker.
        This version is robust against excessive nanosecond precision and relies on 
        strptime for broader Python version compatibility.
        If parsing fails, returns the raw Docker string for debugging.
        """
        if not started_at_str:
            return "N/A"

        s = started_at_str # Вводим переменную s для работы внутри блока try

        try:
            # Docker format: YYYY-MM-DDTHH:MM:SS.nnnnnnnnnZ

            # 1. Заменяем 'Z' (Zulu time) на явное смещение +00:00
            s = s.replace('Z', '+00:00')

            # 2. Обрезаем избыточные наносекунды (оставляем только 6 знаков - микросекунды)
            dot_index = s.find('.')
            tz_index = s.find('+') # Находим начало часового пояса (+00:00)

            if dot_index != -1 and tz_index != -1:
                # Длина дробной части
                frac_len = tz_index - (dot_index + 1)

                if frac_len > 6:
                    # Обрезаем: берем строку до точки + точка + 6 знаков + остаток строки (таймзона)
                    s = s[:dot_index + 1 + 6] + s[tz_index:]
                elif frac_len == 0:
                    # Если есть точка, но нет цифр, удаляем точку
                    s = s[:dot_index] + s[tz_index:]

            # --- Используем strptime с fallback для совместимости с более старыми версиями Python ---
            try:
                # Попытка парсинга с микросекундами (наиболее вероятный случай после обрезки)
                started_at = datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M:%S.%f%z")
            except ValueError:
                # Если парсинг с микросекундами не удался (например, их не было)
                try:
                    # Попытка парсинга без микросекунд
                    started_at = datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M:%S%z")
                except ValueError:
                    # Если оба формата не подошли, пробрасываем ошибку для печати RAW-строки
                    raise Exception("Неизвестный формат времени после обработки")

            # Получаем текущее время UTC для сравнения
            now = datetime.datetime.now(timezone.utc)

            diff = now - started_at
            seconds = int(diff.total_seconds())

            if seconds < 0:
                # Контейнер запущен в будущем (маловероятно, но возможно при рассинхроне часов)
                return "Unknown"

            # --- Форматирование времени ---
            if seconds < 60:
                return f"{seconds} сек"
            elif seconds < 3600:
                minutes = seconds // 60
                return f"{minutes} мин"
            elif seconds < 86400:
                hours = seconds // 3600
                minutes = (seconds % 3600) // 60
                return f"{hours} ч {minutes} мин"
            else:
                days = seconds // 86400
                hours = (seconds % 86400) // 3600
                return f"{days} д {hours} ч"
        except Exception as e:
            # В случае ошибки возвращаем исходную строку, чтобы показать то, что не удалось разобрать
            print(f"Error parsing Docker timestamp '{started_at_str}'. Error: {e}")
            return f"Raw: {started_at_str}"


    async def get_containers(self):
        """Retrieve a list of all containers, including uptime data."""
        try:
            containers = self.docker_client.containers.list(all=True)
            result = []
            for container in containers:
                # --- ИСПРАВЛЕНИЕ: Используем явный if/else вместо тернарного оператора ---
                if container.image.tags:
                    image_tag = container.image.tags[0]
                else:
                    image_tag = container.image.short_id

                started_at = None
                # Get the 'StartedAt' field from container attributes
                try:
                    # container.attrs is necessary for reliable StartedAt
                    started_at = container.attrs['State'].get('StartedAt')
                except (KeyError, AttributeError):
                    started_at = None

                result.append({
                    'name': container.name,
                    'status': container.status,
                    'image': image_tag, # Используем готовую переменную
                    'started_at': started_at
                })
            return result
        except Exception as e:
            print(f"Ошибка при получении контейнеров: {e}")
            return []
            
    # Методы get_container_stats, _calculate_cpu_percent, _calculate_memory_percent удалены

    async def start_container(self, container_name):
        """Запустить контейнер"""
        try:
            container = self.docker_client.containers.get(container_name)
            container.start()
            return True
        except Exception as e:
            print(f"Ошибка при запуске контейнера: {e}")
            return False

    async def stop_container(self, container_name):
        """Остановить контейнер"""
        try:
            container = self.docker_client.containers.get(container_name)
            container.stop()
            return True
        except Exception as e:
            print(f"Ошибка при остановке контейнера: {e}")
            return False

    async def restart_container(self, container_name):
        """Перезапустить контейнер"""
        try:
            container = self.docker_client.containers.get(container_name)
            container.restart()
            return True
        except Exception as e:
            print(f"Ошибка при перезапуске контейнера: {e}")
            return False

    async def get_container_logs(self, container_name, lines=20):
        """Получить логи контейнера"""
        try:
            container = self.docker_client.containers.get(container_name)
            logs = container.logs(tail=lines).decode('utf-8')
            return logs
        except Exception as e:
            print(f"Ошибка при получении логов: {e}")
            return f"Ошибка при получении логов: {e}"

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /start"""
        # Опционально: проверка доступа
        user_id = update.effective_user.id
        if hasattr(self, 'allowed_users') and self.allowed_users and user_id not in self.allowed_users:
            await update.message.reply_text("❌ У вас нет доступа к этому боту.")
            return

        # В клавиатуре осталось только "Список контейнеров"
        keyboard = [
            [InlineKeyboardButton("📋 Список контейнеров", callback_data="list")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "🐳 *Docker Bot*\n\nВыберите действие:",
            reply_markup=reply_markup, parse_mode='Markdown'
        )

    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка нажатий на кнопки"""
        query = update.callback_query
        await query.answer()

        if query.data == "list":
            await self.show_containers(query)
        # elif query.data == "stats": удалено
        #     await self.show_stats(query) удалено
        elif query.data == "back":
            await self.start_menu(query)
        elif query.data.startswith("container_"):
            await self.show_container_info(query)
        elif query.data.startswith("action_"):
            await self.handle_action(query)

    async def start_menu(self, query):
        """Показать главное меню"""
        # В клавиатуре осталось только "Список контейнеров"
        keyboard = [
            [InlineKeyboardButton("📋 Список контейнеров", callback_data="list")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "🐳 *Docker Bot*\n\nВыберите действие:",
            reply_markup=reply_markup, parse_mode='Markdown'
        )

    async def show_containers(self, query):
        """Display the list of containers including status, image, and uptime."""
        containers = await self.get_containers()

        if not containers:
            await query.edit_message_text("📋 Контейнеры не найдены")
            return

        message = "📋 *Список контейнеров:*\n\n"
        keyboard = []

        for container in containers:
            # Извлекаем данные из словаря в начале цикла
            status = container['status']
            started_at = container.get('started_at')

            status_emoji = "🟢" if status == 'running' else "🔴"

            # --- Убедимся, что uptime_str определен всегда перед использованием ---
            uptime_str = "N/A"
            if status == 'running' and started_at:
                uptime_str = self._format_uptime(started_at)

            message += f"{status_emoji} `{container['name']}`\n"
            message += f"    Статус: {status}\n"
            message += f"    Образ: {container['image']}\n"
            message += f"    Время работы: {uptime_str}\n\n"

            # Button to view detailed info
            keyboard.append([
                InlineKeyboardButton(
                    f"{'⏹️' if status == 'running' else '▶️'} {container['name']}",
                    callback_data=f"container_{container['name']}"
                )
            ])

        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back")])
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')

    async def show_container_info(self, query):
        """Показать информацию о контейнере"""
        try:
            container_name = query.data.split("_", 1)[1]
        except IndexError:
            await query.edit_message_text("❌ Ошибка: Неверный формат данных для контейнера.", parse_mode='Markdown')
            return

        try:
            container = self.docker_client.containers.get(container_name)
            status = container.status

            # --- Используем явный if/else для совместимости со старыми версиями Python ---
            if container.image.tags:
                image_tag = container.image.tags[0]
            else:
                image_tag = container.image.short_id
            
            message = f"🐳 *{container_name}*\n\n"
            message += f"Статус: {status}\n"
            message += f"Образ: {image_tag}\n\n" 
            # -----------------------------------------------------------------------

            keyboard = []

            if status == 'running':
                keyboard.append([InlineKeyboardButton("⏹️ Остановить", callback_data=f"action_stop_{container_name}")])
                keyboard.append([InlineKeyboardButton("🔄 Перезапустить", callback_data=f"action_restart_{container_name}")])
            else:
                keyboard.append([InlineKeyboardButton("▶️ Запустить", callback_data=f"action_start_{container_name}")])

            keyboard.append([InlineKeyboardButton("📝 Логи", callback_data=f"action_logs_{container_name}")])
            keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="list")])

            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')
        except docker.errors.NotFound:
             await query.edit_message_text(f"❌ Ошибка: Контейнер с именем `{container_name}` не найден.", parse_mode='Markdown')
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка при получении информации о контейнере: {e}", parse_mode='Markdown')

    async def handle_action(self, query):
        """Обработка действий с контейнерами"""
        data = query.data.split("_")
        action = data[1]
        container_name = "_".join(data[2:])

        if action == "start":
            success = await self.start_container(container_name)
            if success:
                await query.edit_message_text(f"✅ Контейнер `{container_name}` запущен", parse_mode='Markdown')
            else:
                await query.edit_message_text(f"❌ Ошибка при запуске контейнера `{container_name}`", parse_mode='Markdown')
        elif action == "stop":
            success = await self.stop_container(container_name)
            if success:
                await query.edit_message_text(f"⏹️ Контейнер `{container_name}` остановлен", parse_mode='Markdown')
            else:
                await query.edit_message_text(f"❌ Ошибка при остановке контейнера `{container_name}`", parse_mode='Markdown')
        elif action == "restart":
            success = await self.restart_container(container_name)
            if success:
                await query.edit_message_text(f"🔄 Контейнер `{container_name}` перезапущен", parse_mode='Markdown')
            else:
                await query.edit_message_text(f"❌ Ошибка при перезапуске контейнера `{container_name}`", parse_mode='Markdown')
        elif action == "logs":
            logs = await self.get_container_logs(container_name, 20)
            
            # Truncate logs if they are too long for Telegram
            if len(logs) > 3000:
                logs = logs[-3000:] + "\n\n... (показаны последние 20 строк)"

            message = f"📝 *Логи `{container_name}`:*\n\n```\n{logs}\n```"
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data=f"container_{container_name}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')

    # async def show_stats(self, query): удален

    def run(self):
        """Запуск бота"""
        if not self.bot_token:
            print("❌ BOT_TOKEN не найден. Установите его в файле .env")
            return
            
        application = Application.builder().token(self.bot_token).build()

        application.add_handler(CommandHandler("start", self.start))
        application.add_handler(CallbackQueryHandler(self.button_handler))

        print("Бот запущен...")
        application.run_polling()

if __name__ == "__main__":
    try:
        bot = DockerBot()
        bot.run()
    except Exception as e:
        print(f"Критическая ошибка при запуске: {e}")
