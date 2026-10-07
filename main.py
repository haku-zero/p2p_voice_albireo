import customtkinter as ctk
from core.runner import AppRunner

if __name__ == "__main__":
    ctk.set_appearance_mode("Dark")
    ctk.set_default_color_theme("blue")
    app = AppRunner()
    app.start()
