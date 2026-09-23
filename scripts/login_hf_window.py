"""Interactive local login. Never prints or writes the token into the project."""
import re
import threading
import tkinter as tk
from tkinter import ttk

import httpx
from huggingface_hub import login, set_client_factory


def main():
    root = tk.Tk()
    root.title("Hugging Face — вход с кнопкой вставки")
    root.geometry("680x350")
    root.resizable(False, False)
    frame = ttk.Frame(root, padding=20)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="Вставьте токен Hugging Face, начинающийся с hf_", wraplength=580).pack(anchor="w")
    entry = ttk.Entry(frame, show="*", width=75)
    entry.pack(fill="x", pady=12)
    status = tk.StringVar(value="Токен передаётся только huggingface.co и сохраняется стандартным клиентом\nв профиле пользователя. В Git и чат он не попадает.")
    ttk.Label(frame, textvariable=status, wraplength=590).pack(anchor="w", pady=8)

    def paste_token():
        # Read only on the user's click. Never print clipboard contents.
        try:
            value = root.clipboard_get().strip()
        except tk.TclError:
            status.set("В буфере нет текста. Нажмите Copy рядом с токеном на сайте и повторите.")
            return
        if not re.fullmatch(r"hf_[A-Za-z0-9_-]+", value):
            status.set("В буфере не токен hf_… Нажмите Copy именно рядом с новым токеном на сайте.")
            return
        entry.delete(0, "end")
        entry.insert(0, value)
        status.set("Токен вставлен и скрыт звёздочками. Теперь нажмите «Войти».")

    ttk.Button(frame, text="Вставить из буфера", command=paste_token).pack(anchor="w", pady=5)

    def finish(message):
        status.set(message)
        button.config(state="normal")

    def authenticate(token):
        try:
            set_client_factory(lambda: httpx.Client(trust_env=False, timeout=30))
            login(token=token, add_to_git_credential=False)
            message = "Вход выполнен. Можно закрыть окно и написать в Codex: готово."
        except Exception as exc:
            response = getattr(exc, "response", None)
            code = getattr(response, "status_code", None)
            if code == 401:
                message = "Hugging Face отклонил токен (401). Проверьте, что он действующий и скопирован полностью."
            elif code == 400:
                message = "Сервер вернул 400 даже после проверки формата. Попробуйте создать новый токен Read и повторить."
            elif code:
                message = f"Hugging Face вернул HTTP {code}. Сообщите только этот код, не токен."
            else:
                message = f"Не удалось завершить вход: {type(exc).__name__}. Сообщите название ошибки, не токен."
        root.after(0, finish, message)

    def submit():
        token = entry.get().strip()
        if not re.fullmatch(r"hf_[A-Za-z0-9_-]+", token):
            status.set("Вставлен не сам токен или есть лишние символы. Нужна строка hf_… без кавычек, русских букв и пробелов.")
            return
        entry.delete(0, "end")
        button.config(state="disabled")
        status.set("Проверяю вход…")
        threading.Thread(target=authenticate, args=(token,), daemon=True).start()

    button = ttk.Button(frame, text="Войти", command=submit)
    button.pack(anchor="w", pady=12)
    entry.focus_set()
    root.mainloop()


if __name__ == "__main__":
    main()
