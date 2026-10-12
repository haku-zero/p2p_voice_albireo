import json
import customtkinter as ctk
from utils.config import load_config, save_config
from ui.theme import *

class NetworkSettingsModal:
    def __init__(self, root):
        self.root = root

    def open(self):
        modal = ctk.CTkToplevel(self.root)
        modal.title("NAT Traversal & Relay Settings")
        modal.geometry("540x520")
        modal.transient(self.root)
        modal.grab_set()
        modal.configure(fg_color=BG_COLOR)
        
        ctk.CTkLabel(modal, text="NAT Traversal & Relay Configuration", font=("Consolas", 15, "bold"), text_color=PRIMARY).pack(pady=(16, 8))
        
        cfg = load_config()
        force_relay_var = ctk.BooleanVar(value=cfg.get("force_relay", False))
        
        switch_frame = ctk.CTkFrame(modal, fg_color=FRAME_COLOR, corner_radius=6, border_color=BORDER_COLOR, border_width=1)
        switch_frame.pack(fill="x", padx=20, pady=(0, 10))
        
        switch = ctk.CTkSwitch(
            switch_frame, 
            text="Force TURN Relay Only (Bypass Symmetric NAT / Strict Firewalls)", 
            variable=force_relay_var, 
            progress_color=ACCENT, 
            text_color=TEXT_COLOR, 
            font=FONT_MAIN
        )
        switch.pack(padx=12, pady=10, anchor="w")
        
        header_row = ctk.CTkFrame(modal, fg_color="transparent")
        header_row.pack(fill="x", padx=20, pady=(4, 4))
        
        ctk.CTkLabel(header_row, text="ICE Servers (JSON format)", font=FONT_BOLD, text_color=SECONDARY).pack(side="left")
        
        def insert_turn_template():
            sample_turn = [
                {"urls": ["stun:stun.l.google.com:19302"]},
                {
                    "urls": ["turn:turn.matrix.org:3478?transport=udp", "turn:turn.matrix.org:3478?transport=tcp"],
                    "username": "example_user",
                    "credential": "example_password"
                }
            ]
            textbox.delete("1.0", "end")
            textbox.insert("1.0", json.dumps(sample_turn, indent=4))
            
        btn_preset = ctk.CTkButton(
            header_row, 
            text="Load TURN Template", 
            font=FONT_MAIN, 
            width=130, 
            height=24, 
            corner_radius=4,
            fg_color="transparent", 
            border_width=1, 
            border_color=SECONDARY, 
            text_color=SECONDARY, 
            hover_color=SECONDARY_HOV,
            command=insert_turn_template
        )
        btn_preset.pack(side="right")
        
        textbox = ctk.CTkTextbox(modal, width=500, height=240, font=("Consolas", 12), fg_color=FRAME_COLOR, border_color=BORDER_COLOR, border_width=1, text_color=TEXT_COLOR)
        textbox.pack(padx=20, pady=(4, 10))
        
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
                save_config("force_relay", force_relay_var.get())
                modal.destroy()
            except Exception as e:
                import tkinter.messagebox
                tkinter.messagebox.showerror("JSON Error", str(e))
                
        btn_save = ctk.CTkButton(
            modal, 
            text="Save Settings (Requires Restart)", 
            font=FONT_BOLD, 
            corner_radius=4, 
            fg_color="transparent", 
            border_width=1, 
            border_color=SUCCESS, 
            text_color=SUCCESS, 
            hover_color=SUCCESS_HOV, 
            command=save
        )
        btn_save.pack(pady=10)
