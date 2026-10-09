import threading
import customtkinter as ctk
import pystray
from PIL import Image, ImageDraw
from utils import config
from ui.theme import *
from utils.i18n import get_text as _T

class MainWindow(ctk.CTk):
    """
    Main Application Window.
    Handles top-level window rendering, system tray, and the login flow UI.
    """
    def __init__(self, enter_room_callback, quit_callback):
        super().__init__()
        self.enter_room_callback = enter_room_callback
        self.quit_callback = quit_callback
        self.title("Albireo")
        self.geometry("850x680")
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.tray_icon = None
        self.local_id = "User"
        self.callsign = "User"

    def show_id_selection(self):
        for widget in self.winfo_children():
            widget.destroy()
        self.configure(fg_color=BG_COLOR)
        frame = ctk.CTkFrame(self, fg_color=FRAME_COLOR, corner_radius=0, border_width=1, border_color=BORDER_COLOR)
        frame.pack(pady=100, padx=50, fill="both", expand=True)
        ctk.CTkLabel(frame, text=_T("sys_init"), font=FONT_TITLE, text_color=PRIMARY).pack(pady=30)
        self.id_entry = ctk.CTkEntry(frame, placeholder_text=_T("input_callsign"), height=40, corner_radius=0, font=FONT_MAIN, border_color=PRIMARY, fg_color=BG_COLOR, text_color=PRIMARY)
        
        saved_id = config.load_config().get("local_id", "")
        if saved_id:
            self.id_entry.insert(0, saved_id)
            
        self.id_entry.pack(pady=20, padx=50, fill="x")
        self.id_entry.bind("<Return>", lambda e: self.submit_id())
        ctk.CTkButton(frame, text=_T("establish"), height=45, corner_radius=0, font=FONT_TITLE, fg_color="transparent", border_width=1, border_color=PRIMARY, text_color=PRIMARY, hover_color=PRIMARY_HOV, command=self.submit_id).pack(pady=10, padx=50, fill="x")

        # Language Selector
        lang_frame = ctk.CTkFrame(self, fg_color="transparent")
        lang_frame.pack(side="bottom", pady=20)
        ctk.CTkLabel(lang_frame, text=_T("lang_label"), font=("Consolas", 12), text_color="#94A3B8").pack(side="left", padx=5)
        
        current_lang = config.load_config().get("lang", "en")
        lang_combo = ctk.CTkComboBox(lang_frame, values=["English", "中文"], width=100, font=("Consolas", 12), fg_color="#111726", border_color="#1E293B", button_color="#1E293B", text_color="#00F0FF")
        lang_combo.set("English" if current_lang == "en" else "中文")
        
        def change_lang(choice):
            config.save_config("lang", "en" if choice == "English" else "zh")
            self.show_id_selection()
        lang_combo.configure(command=change_lang)
        lang_combo.pack(side="left")

    def submit_id(self):
        uid = self.id_entry.get().strip()
        if not uid: return
        self.callsign = uid
        config.save_config("local_id", uid)
        self.enter_room_callback(uid)

    def on_closing(self):
        cfg = config.load_config()
        saved_action = cfg.get("close_action")
        
        if saved_action == "close":
            self.quit_callback()
            return
        elif saved_action == "minimize":
            self.hide_window()
            return

        dialog = ctk.CTkToplevel(self)
        dialog.title("EXIT")
        dialog.geometry("400x180")
        dialog.transient(self)
        dialog.grab_set()
        dialog.configure(fg_color="#090C15")
        
        ctk.CTkLabel(dialog, text=_T("term"), font=("Consolas", 15, "bold"), text_color="#FF003C").pack(pady=(20, 5))
        
        remember_var = ctk.BooleanVar(value=False)
        chk = ctk.CTkCheckBox(dialog, text=_T("mem"), variable=remember_var, font=("Consolas", 11), fg_color="#00F0FF", border_color="#00F0FF", hover_color="#004455", text_color="#94A3B8")
        chk.pack(pady=(0, 15))
        
        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack()
        
        def do_close():
            if remember_var.get():
                config.save_config("close_action", "close")
            dialog.destroy()
            self.quit_callback()
            
        def do_minimize():
            if remember_var.get():
                config.save_config("close_action", "minimize")
            dialog.destroy()
            self.hide_window()
            
        ctk.CTkButton(btn_frame, text=_T("min"), corner_radius=2, font=("Consolas", 12), fg_color="transparent", border_width=1, border_color="#00F0FF", text_color="#00F0FF", hover_color="#004455", command=do_minimize, width=170).pack(side="left", padx=10)
        ctk.CTkButton(btn_frame, text=_T("dest"), corner_radius=2, font=("Consolas", 12), fg_color="transparent", border_width=1, border_color="#FF003C", text_color="#FF003C", hover_color="#550011", command=do_close, width=170).pack(side="left", padx=10)

    def hide_window(self):
        self.withdraw()
        if self.tray_icon is None:
            image = Image.new('RGB', (64, 64), color=(43, 45, 48))
            draw = ImageDraw.Draw(image)
            draw.ellipse((16, 16, 48, 48), fill=(16, 185, 129))
            
            menu = pystray.Menu(
                pystray.MenuItem("Albireo P2P", self.show_window, default=True),
                pystray.MenuItem("Exit", self.quit_window)
            )
            self.tray_icon = pystray.Icon("albireo", image, "Albireo", menu)
            threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def show_window(self, icon, item):
        self.after(0, self.deiconify)

    def quit_window(self, icon, item):
        icon.stop()
        self.after(0, self.quit_callback)
