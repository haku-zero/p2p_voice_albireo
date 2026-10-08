import customtkinter as ctk
from ui.theme import *

class ToastManager:
    def __init__(self, root):
        self.root = root
        self.active_toasts = []

    def show_toast(self, message):
        toast = ctk.CTkFrame(self.root, fg_color=PRIMARY, corner_radius=0)
        lbl = ctk.CTkLabel(toast, text=f"[ SYS ] {message}", text_color=BG_COLOR, font=FONT_BOLD)
        lbl.pack(padx=20, pady=10)
        
        y_offset = 20 + len(self.active_toasts) * 60
        toast.place(relx=0.5, y=y_offset, anchor="n")
        
        self.active_toasts.append(toast)
        
        def _hide():
            if toast.winfo_exists():
                toast.destroy()
            if toast in self.active_toasts:
                self.active_toasts.remove(toast)
            self._rearrange_toasts()
            
        self.root.after(3000, _hide)

    def _rearrange_toasts(self):
        for i, t in enumerate(self.active_toasts):
            if t.winfo_exists():
                t.place_configure(relx=0.5, y=20 + i * 60, anchor="n")
