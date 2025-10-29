import base64
import tkinter as tk
from tkinter import messagebox, filedialog
from Crypto.Cipher import AES
from Crypto.Protocol.KDF import PBKDF2
from Crypto.Random import get_random_bytes
import random
import struct
import hashlib

# ================== Класс шифрования ==================

# Функция для вычисления детерминированного числа итераций из пароля
def calculate_iterations_from_password(password: str, iterations_password: str) -> int:
    """
    Вычисляет количество итераций на основе хеша связки двух паролей.
    Если второй пароль пуст, используется только основной.
    """
    combined_password = password + iterations_password
    hash_value = hashlib.sha256(combined_password.encode('utf-8')).digest()
    hash_int = struct.unpack('>I', hash_value[:4])[0]
    
    min_iter = 5000000
    max_iter = 6000000
    
    iterations = min_iter + (hash_int % (max_iter - min_iter + 1))
    return iterations

class AESGCMCipher:
    def __init__(self, password, iterations_password=""):
        self.password = password.encode('utf-8')
        self.iterations_password = iterations_password.encode('utf-8')

    def encrypt(self, data: bytes, iterations: int) -> bytes:
        salt = get_random_bytes(16)
        key = PBKDF2(self.password, salt, dkLen=32, count=iterations)

        cipher = AES.new(key, AES.MODE_GCM)
        ciphertext, tag = cipher.encrypt_and_digest(data)
        
        return salt + cipher.nonce + ciphertext + tag

    def decrypt(self, packet: bytes, decrypt_iterations: int) -> bytes:
        try:
            salt = packet[:16]
            nonce = packet[16:32]
            ciphertext = packet[32:-16]
            tag = packet[-16:]
            
            key = PBKDF2(self.password, salt, dkLen=32, count=decrypt_iterations)
            
            cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
            plaintext = cipher.decrypt_and_verify(ciphertext, tag)
            return plaintext
        except ValueError as e:
            # Если не удалось, пробуем с вычисленным из пароля количеством итераций
            try:
                iterations = calculate_iterations_from_password(
                    self.password.decode('utf-8'),
                    self.iterations_password.decode('utf-8')
                )
                
                salt = packet[:16]
                nonce = packet[16:32]
                ciphertext = packet[32:-16]
                tag = packet[-16:]
                
                key = PBKDF2(self.password, salt, dkLen=32, count=iterations)

                cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
                plaintext = cipher.decrypt_and_verify(ciphertext, tag)
                return plaintext
            except ValueError:
                raise ValueError("Ошибка расшифрования: повреждённые данные или неверный пароль") from e


# ================== GUI Функции ==================
def encrypt_text():
    password = key_entry.get()
    iterations_password = iterations_key_entry.get()
    text = message_text.get("1.0", tk.END).rstrip("\n")
    
    if not password or not text:
        messagebox.showerror("Ошибка", "Введите пароль и текст!")
        return

    try:
        iterations = 0
        if iterations_password.strip() != "":
            iterations = calculate_iterations_from_password(password, iterations_password)
        else:
            if encrypt_iter_entry.get().strip() == "":
                iterations = random.randint(5000000, 6000000)
            else:
                iterations = int(encrypt_iter_entry.get())
                if iterations < 5000000:
                    messagebox.showerror("Ошибка", "Количество итераций для шифрования должно быть не менее 5 000 000!")
                    return
    except ValueError:
        messagebox.showerror("Ошибка", "Количество итераций для шифрования должно быть числом!")
        return

    try:
        cipher = AESGCMCipher(password, iterations_password)
        encrypted_data = cipher.encrypt(text.encode('utf-8'), iterations)

        result_text.config(state=tk.NORMAL)
        result_text.delete("1.0", tk.END)
        result_text.insert(tk.END, base64.b64encode(encrypted_data).decode('utf-8'))
        result_text.config(state=tk.DISABLED)
        
        # Обновляем поле с итерациями
        iterations_result_text.config(state=tk.NORMAL)
        iterations_result_text.delete("1.0", tk.END)
        iterations_result_text.insert(tk.END, str(iterations))
        iterations_result_text.config(state=tk.DISABLED)

        messagebox.showinfo("Успех", "Текст зашифрован и отображён в поле «Результат»")
    except Exception as e:
        messagebox.showerror("Ошибка", f"Не удалось зашифровать: {e}")


def decrypt_text():
    password = key_entry.get()
    iterations_password = iterations_key_entry.get()
    text = message_text.get("1.0", tk.END).rstrip("\n")

    if not password or not text:
        messagebox.showerror("Ошибка", "Введите пароль и зашифрованный текст")
        return

    try:
        encrypted_data = base64.b64decode(text)
        
        decrypt_iterations = 0
        if decrypt_iter_entry.get().strip() == "":
            decrypt_iterations = 100000
        else:
            try:
                decrypt_iterations = int(decrypt_iter_entry.get())
            except ValueError:
                messagebox.showerror("Ошибка", "Количество итераций для расшифровки должно быть числом!")
                return

        cipher = AESGCMCipher(password, iterations_password)
        decrypted_data = cipher.decrypt(encrypted_data, decrypt_iterations)
        
        decrypted_text = decrypted_data.decode('utf-8')

        result_text.config(state=tk.NORMAL)
        result_text.delete("1.0", tk.END)
        result_text.insert(tk.END, decrypted_text)
        result_text.config(state=tk.DISABLED)
        messagebox.showinfo("Успех", "Текст успешно расшифрован и отображён в поле «Результат»")
    except Exception as e:
        messagebox.showerror("Ошибка", f"Не удалось расшифровать: {e}")


def encrypt_file():
    password = key_entry.get()
    iterations_password = iterations_key_entry.get()
    if not password:
        messagebox.showerror("Ошибка", "Введите пароль!")
        return
    
    try:
        iterations = 0
        if iterations_password.strip() != "":
            iterations = calculate_iterations_from_password(password, iterations_password)
        else:
            if encrypt_iter_entry.get().strip() == "":
                iterations = random.randint(5000000, 6000000)
            else:
                iterations = int(encrypt_iter_entry.get())
                if iterations < 5000000:
                    messagebox.showerror("Ошибка", "Количество итераций для шифрования должно быть не менее 5 000 000!")
                    return
    except ValueError:
        messagebox.showerror("Ошибка", "Количество итераций для шифрования должно быть числом!")
        return


    file_path = filedialog.askopenfilename(title="Выберите файл для шифрования")
    if not file_path:
        return

    save_path = filedialog.asksaveasfilename(title="Сохранить зашифрованный файл как...", defaultextension=".enc")
    if not save_path:
        return

    try:
        cipher = AESGCMCipher(password, iterations_password)
        with open(file_path, 'rb') as f_in:
            data = f_in.read()
        
        encrypted_data = cipher.encrypt(data, iterations)

        with open(save_path, 'wb') as f_out:
            f_out.write(encrypted_data)

        # Обновляем поле с итерациями
        iterations_result_text.config(state=tk.NORMAL)
        iterations_result_text.delete("1.0", tk.END)
        iterations_result_text.insert(tk.END, str(iterations))
        iterations_result_text.config(state=tk.DISABLED)

        messagebox.showinfo("Успех", "Файл успешно зашифрован!")
    except Exception as e:
        messagebox.showerror("Ошибка", f"Не удалось зашифровать файл: {e}")


def decrypt_file():
    password = key_entry.get()
    iterations_password = iterations_key_entry.get()
    if not password:
        messagebox.showerror("Ошибка", "Введите пароль!")
        return

    file_path = filedialog.askopenfilename(title="Выберите файл для расшифрования")
    if not file_path:
        return

    save_path = filedialog.asksaveasfilename(title="Сохранить расшифрованный файл как...")
    if not save_path:
        return

    try:
        with open(file_path, 'rb') as f_in:
            encrypted_data = f_in.read()

        decrypt_iterations = 0
        if decrypt_iter_entry.get().strip() == "":
            decrypt_iterations = 100000
        else:
            try:
                decrypt_iterations = int(decrypt_iter_entry.get())
            except ValueError:
                messagebox.showerror("Ошибка", "Количество итераций для расшифровки должно быть числом!")
                return
        
        cipher = AESGCMCipher(password, iterations_password)
        decrypted_data = cipher.decrypt(encrypted_data, decrypt_iterations)

        with open(save_path, 'wb') as f_out:
            f_out.write(decrypted_data)

        messagebox.showinfo("Успех", "Файл успешно расшифрован!")
    except Exception as e:
        messagebox.showerror("Ошибка", f"Не удалось расшифровать файл: {e}")


def copy_result():
    result = result_text.get("1.0", tk.END).strip()
    if result:
        root.clipboard_clear()
        root.clipboard_append(result)
        messagebox.showinfo("Копирование", "Результат скопирован в буфер обмена")
    else:
        messagebox.showwarning("Копирование", "Поле результата пустое")

def copy_iterations():
    iterations_result = iterations_result_text.get("1.0", tk.END).strip()
    if iterations_result:
        root.clipboard_clear()
        root.clipboard_append(iterations_result)
        messagebox.showinfo("Копирование", "Количество итераций скопировано в буфер обмена")
    else:
        messagebox.showwarning("Копирование", "Поле итераций пустое")

def clear_all():
    message_text.delete("1.0", tk.END)
    key_entry.delete(0, tk.END)
    iterations_key_entry.delete(0, tk.END)
    encrypt_iter_entry.delete(0, tk.END)
    decrypt_iter_entry.delete(0, tk.END)
    result_text.config(state=tk.NORMAL)
    result_text.delete("1.0", tk.END)
    result_text.config(state=tk.DISABLED)
    iterations_result_text.config(state=tk.NORMAL)
    iterations_result_text.delete("1.0", tk.END)
    iterations_result_text.config(state=tk.DISABLED)


# ================== Интерфейс ==================
root = tk.Tk()
root.title("AES-GCM Secure Encryptor")

# === Блок для пароля ===
pass_frame = tk.LabelFrame(root, text="Ключевой пароль", padx=10, pady=10)
pass_frame.pack(pady=10, padx=10, fill="x", expand=True)

key_label = tk.Label(pass_frame, text="Введите пароль:")
key_label.pack()
key_entry = tk.Entry(pass_frame, width=60)
key_entry.pack(fill=tk.X, expand=True)

# === Блок для итераций ===
iter_frame = tk.LabelFrame(root, text="Настройки итераций", padx=10, pady=10)
iter_frame.pack(pady=10, padx=10, fill="x", expand=True)

iterations_key_label = tk.Label(iter_frame, text="Пароль для итераций (опционально):")
iterations_key_label.pack(side=tk.LEFT, padx=5)
iterations_key_entry = tk.Entry(iter_frame, width=15)
iterations_key_entry.pack(side=tk.LEFT, padx=5)

encrypt_iter_label = tk.Label(iter_frame, text="Итерации (мин. 5 000 000, пусто - случайное):")
encrypt_iter_label.pack(side=tk.LEFT, padx=5)
encrypt_iter_entry = tk.Entry(iter_frame, width=15)
encrypt_iter_entry.pack(side=tk.LEFT, padx=5)

decrypt_iter_label = tk.Label(iter_frame, text="Итерации для расшифровки (пусто - 100 000):")
decrypt_iter_label.pack(side=tk.LEFT, padx=5)
decrypt_iter_entry = tk.Entry(iter_frame, width=15)
decrypt_iter_entry.pack(side=tk.LEFT, padx=5)


# === Блок для текста ===
text_frame = tk.LabelFrame(root, text="Шифрование/Расшифрование текста", padx=10, pady=10)
text_frame.pack(pady=10, padx=10, fill="x", expand=True)

message_label = tk.Label(text_frame, text="Введите текст:")
message_label.pack()
message_text = tk.Text(text_frame, height=5)
message_text.pack(pady=5, fill=tk.X, expand=True)

text_button_frame = tk.Frame(text_frame)
text_button_frame.pack(pady=5)

encrypt_text_button = tk.Button(text_button_frame, text="Зашифровать текст", command=encrypt_text)
encrypt_text_button.pack(side=tk.LEFT, padx=5)

decrypt_text_button = tk.Button(text_button_frame, text="Расшифровать текст", command=decrypt_text)
decrypt_text_button.pack(side=tk.LEFT, padx=5)

# === Блок результата ===
result_frame = tk.LabelFrame(root, text="Результат (для текста)", padx=10, pady=10)
result_frame.pack(pady=10, padx=10, fill="both", expand=True)

result_text = tk.Text(result_frame, height=5, state=tk.DISABLED)
result_text.pack(fill="both", expand=True)

# === Блок для вывода итераций ===
iterations_frame = tk.LabelFrame(root, text="Использованные итерации", padx=10, pady=10)
iterations_frame.pack(pady=10, padx=10, fill="x", expand=True)

iterations_result_text = tk.Text(iterations_frame, height=1, state=tk.DISABLED)
iterations_result_text.pack(side=tk.LEFT, fill=tk.X, expand=True)

copy_iterations_button = tk.Button(iterations_frame, text="Копировать итерации", command=copy_iterations)
copy_iterations_button.pack(side=tk.RIGHT, padx=5)

# === Кнопки дополнительных действий ===
button_frame = tk.Frame(root)
button_frame.pack(pady=5)

copy_button = tk.Button(button_frame, text="Копировать результат", command=copy_result)
copy_button.pack(side=tk.LEFT, padx=5)

clear_button = tk.Button(button_frame, text="Очистить всё", command=clear_all)
clear_button.pack(side=tk.LEFT, padx=5)

# === Блок для файлов ===
file_frame = tk.LabelFrame(root, text="Шифрование/Расшифрование файлов", padx=10, pady=10)
file_frame.pack(pady=10, padx=10, fill="x", expand=True)

file_button_frame = tk.Frame(file_frame)
file_button_frame.pack(pady=5)

encrypt_file_button = tk.Button(file_button_frame, text="Зашифровать файл", command=encrypt_file)
encrypt_file_button.pack(side=tk.LEFT, padx=5)

decrypt_file_button = tk.Button(file_button_frame, text="Расшифровать файл", command=decrypt_file)
decrypt_file_button.pack(side=tk.LEFT, padx=5)

root.mainloop()