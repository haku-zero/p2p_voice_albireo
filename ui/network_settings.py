import json
import customtkinter as ctk
from utils.config import load_config, save_config
from ui.theme import *

class NetworkSettingsModal:
    def __init__(self, root):
        self.root = root

    def open(self):
        modal = ctk.CTkToplevel(self.root)
        modal.title("NAT Traversal (STUN/TURN) Settings")
        modal.geometry("500x400")
        modal.transient(self.root)
        modal.grab_set()
        modal.configure(fg_color=BG_COLOR)
        
        ctk.CTkLabel(modal, text="ICE Servers (JSON format)", font=FONT_BOLD, text_color=PRIMARY).pack(pady=(20, 10))
        
        textbox = ctk.CTkTextbox(modal, width=460, height=250, font=("Consolas", 12), fg_color=FRAME_COLOR, border_color=BORDER_COLOR, border_width=1, text_color=TEXT_COLOR)
        textbox.pack(padx=20, pady=10)
        
        cfg = load_config()
        default_ice = [
            {"urls": ["stun:stun.l.google.com:19302"]},
            {"urls": ["stun:global.stun.twilio.com:3478"]}
        ]
        current_ice = cfg.get("ice_servers", default_ice)
        textbox.insert("1.0", json.dumps(current_ice, indent=4))
        
        def save():
            try:
                parsed = json.loads(textbox.get("1.0", "end").strip())
                if not isinstance(parsed, list):
                    raise ValueError("Must be a JSON list.")
                save_config("ice_servers", parsed)
                modal.destroy()
            except Exception as e:
                import tkinter.messagebox
                tkinter.messagebox.showerror("JSON Error", str(e))
                
        btn_save = ctk.CTkButton(modal, text="Save Settings (Requires Restart)", font=FONT_BOLD, corner_radius=0, fg_color="transparent", border_width=1, border_color=SUCCESS, text_color=SUCCESS, hover_color="#004433", command=save)
        btn_save.pack(pady=10)
