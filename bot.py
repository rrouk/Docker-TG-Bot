import os
import asyncio
import docker
import html # Импорт модуля html для экранирования
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from dotenv import load_dotenv
import datetime
from datetime import timezone 

load_dotenv()

class DockerBot:
    def __init__(self):
        self.bot_token = os.getenv('BOT_TOKEN')
        self.allowed_users = [int(user_id) for user_id in os.getenv('ALLOWED_USERS', '').split(',') if user_id]
        
        try:
            if not os.path.exists('/var/run/docker.sock'):
                raise Exception("Docker socket не найден: /var/run/docker.sock")

            self.docker_client = docker.DockerClient(base_url='unix:///var/run/docker.sock')
            self.docker_client.ping()
            print("Docker подключение успешно установлено")
        except Exception as e:
            print(f"Ошибка подключения к Docker: {e}")
            print("Убедитесь, что Docker socket смонтирован в контейнер")
            raise

    # --- Новая функция для экранирования системных данных ---
    def _escape_html(self, text):
        """Экранирует специальные символы HTML для безопасного отображения"""
        return html.escape(str(text))
    # --------------------------------------------------------

    def _format_uptime(self, started_at_str):
        """
        Calculates and formats the uptime from the ISO 8601 string returned by Docker.
        """
        if not started_at_str:
            return "N/A"

        s = started_at_str

        try:
            s = s.replace('Z', '+00:00')
            dot_index = s.find('.')
            tz_index = s.find('+') 

            if dot_index != -1 and tz_index != -1:
                frac_len = tz_index - (dot_index + 1)
                if frac_len > 6:
                    s = s[:dot_index + 1 + 6] + s[tz_index:]
                elif frac_len == 0:
                    s = s[:dot_index] + s[tz_index:]

            try:
                started_at = datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M:%S.%f%z")
            except ValueError:
                started_at = datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M:%S%z")

            now = datetime.datetime.now(timezone.utc)
            diff = now - started_at
            seconds = int(diff.total_seconds())

            if seconds < 0:
                return "Unknown"

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
            print(f"Error parsing Docker timestamp '{started_at_str}'. Error: {e}")
            return f"Raw: {started_at_str}"


    async def get_containers(self):
        """Retrieve a list of all containers, including uptime data."""
        try:
            containers = self.docker_client.containers.list(all=True)
            result = []
            for container in containers:
                if container.image.tags:
                    image_tag = container.image.tags[0]
                else:
                    image_tag = container.image.short_id

                started_at = None
                try:
                    started_at = container.attrs['State'].get('StartedAt')
                except (KeyError, AttributeError):
                    started_at = None

                result.append({
                    'name': container.name,
                    'status': container.status,
                    'image': image_tag,
                    'started_at': started_at
                })
            return result
        except Exception as e:
            print(f"Ошибка при получении контейнеров: {e}")
            return []

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
            return f"Ошибка при получении логов: {self._escape_html(e)}"

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /start"""
        user_id = update.effective_user.id
        if hasattr(self, 'allowed_users') and self.allowed_users and user_id not in self.allowed_users:
            await update.message.reply_text("❌ У вас нет доступа к этому боту.")
            return

        keyboard = [
            [InlineKeyboardButton("📋 Список контейнеров", callback_data="list")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # parse_mode='HTML'
        await update.message.reply_text(
            "🐳 <b>Docker Bot</b>\n\nВыберите действие:",
            reply_markup=reply_markup, parse_mode='HTML'
        )

    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка нажатий на кнопки"""
        query = update.callback_query
        await query.answer()

        if query.data == "list":
            await self.show_containers(query)
        elif query.data == "back":
            await self.start_menu(query)
        elif query.data.startswith("container_"):
            await self.show_container_info(query)
        elif query.data.startswith("action_"):
            await self.handle_action(query)

    async def start_menu(self, query):
        """Показать главное меню"""
        keyboard = [
            [InlineKeyboardButton("📋 Список контейнеров", callback_data="list")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # parse_mode='HTML'
        await query.edit_message_text(
            "🐳 <b>Docker Bot</b>\n\nВыберите действие:",
            reply_markup=reply_markup, parse_mode='HTML'
        )

    async def show_containers(self, query):
        """Display the list of containers including status, image, and uptime."""
        containers = await self.get_containers()

        if not containers:
            # parse_mode='HTML'
            await query.edit_message_text("📋 Контейнеры не найдены", parse_mode='HTML')
            return

        # Замена * на <b>
        message = "📋 <b>Список контейнеров:</b>\n\n"
        keyboard = []

        for container in containers:
            status = container['status']
            started_at = container.get('started_at')

            status_emoji = "🟢" if status == 'running' else "🔴"

            uptime_str = "N/A"
            if status == 'running' and started_at:
                uptime_str = self._format_uptime(started_at)
            
            # Используем <code> для контейнера и image, чтобы избежать ошибок парсинга
            escaped_name = self._escape_html(container['name'])
            escaped_image = self._escape_html(container['image'])
            
            message += f"{status_emoji} <code>{escaped_name}</code>\n"
            message += f"    Статус: {status}\n"
            message += f"    Образ: {escaped_image}\n"
            message += f"    Время работы: {uptime_str}\n\n"

            # Кнопки остаются прежними, так как они не используют разметку
            keyboard.append([
                InlineKeyboardButton(
                    f"{'⏹️' if status == 'running' else '▶️'} {container['name']}",
                    callback_data=f"container_{container['name']}"
                )
            ])

        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back")])
        reply_markup = InlineKeyboardMarkup(keyboard)

        # parse_mode='HTML'
        await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='HTML')

    async def show_container_info(self, query):
        """Показать информацию о контейнере"""
        try:
            container_name = query.data.split("_", 1)[1]
        except IndexError:
            await query.edit_message_text("❌ Ошибка: Неверный формат данных для контейнера.", parse_mode='HTML')
            return

        try:
            container = self.docker_client.containers.get(container_name)
            status = container.status

            if container.image.tags:
                image_tag = container.image.tags[0]
            else:
                image_tag = container.image.short_id

            escaped_name = self._escape_html(container_name)
            escaped_image = self._escape_html(image_tag)
            
            # Замена * на <b> и ` на <code>
            message = f"🐳 <b>{escaped_name}</b>\n\n"
            message += f"Статус: {status}\n"
            message += f"Образ: <code>{escaped_image}</code>\n\n"

            keyboard = []

            if status == 'running':
                keyboard.append([InlineKeyboardButton("⏹️ Остановить", callback_data=f"action_stop_{container_name}")])
                keyboard.append([InlineKeyboardButton("🔄 Перезапустить", callback_data=f"action_restart_{container_name}")])
            else:
                keyboard.append([InlineKeyboardButton("▶️ Запустить", callback_data=f"action_start_{container_name}")])

            keyboard.append([InlineKeyboardButton("📝 Логи", callback_data=f"action_logs_{container_name}")])
            keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="list")])

            reply_markup = InlineKeyboardMarkup(keyboard)
            # parse_mode='HTML'
            await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='HTML')
        except docker.errors.NotFound:
             await query.edit_message_text(f"❌ Ошибка: Контейнер с именем <code>{self._escape_html(container_name)}</code> не найден.", parse_mode='HTML')
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка при получении информации о контейнере: {self._escape_html(e)}", parse_mode='HTML')

    async def handle_action(self, query):
        """Обработка действий с контейнерами"""
        data = query.data.split("_")
        action = data[1]
        container_name = "_".join(data[2:])
        escaped_name = self._escape_html(container_name)

        if action == "start":
            success = await self.start_container(container_name)
            if success:
                await query.edit_message_text(f"✅ Контейнер <code>{escaped_name}</code> запущен", parse_mode='HTML')
            else:
                await query.edit_message_text(f"❌ Ошибка при запуске контейнера <code>{escaped_name}</code>", parse_mode='HTML')
        elif action == "stop":
            success = await self.stop_container(container_name)
            if success:
                await query.edit_message_text(f"⏹️ Контейнер <code>{escaped_name}</code> остановлен", parse_mode='HTML')
            else:
                await query.edit_message_text(f"❌ Ошибка при остановке контейнера <code>{escaped_name}</code>", parse_mode='HTML')
        elif action == "restart":
            success = await self.restart_container(container_name)
            if success:
                await query.edit_message_text(f"🔄 Контейнер <code>{escaped_name}</code> перезапущен", parse_mode='HTML')
            else:
                await query.edit_message_text(f"❌ Ошибка при перезапуске контейнера <code>{escaped_name}</code>", parse_mode='HTML')
        elif action == "logs":
            logs = await self.get_container_logs(container_name, 20)
            
            if len(logs) > 3000:
                logs = logs[-3000:] + "\n\n... (показаны последние 20 строк)"

            # Используем <pre> для логов и экранируем весь текст логов
            escaped_logs = self._escape_html(logs)
            message = f"📝 <b>Логи <code>{escaped_name}</code>:</b>\n\n<pre>{escaped_logs}</pre>"
            
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data=f"container_{container_name}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)

            # parse_mode='HTML'
            await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='HTML')


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
