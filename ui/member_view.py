import customtkinter as ctk
from utils.i18n import get_text as _T
from ui.theme import *

class MemberView:
    def __init__(self, parent_frame):
        self.frame = parent_frame
        self.member_labels = {}

    def add_member(self, member_id, name):
        row = ctk.CTkFrame(self.frame, fg_color="transparent", border_width=1, border_color=BORDER_COLOR)
        row.pack(fill="x", pady=5, padx=5)
        indicator = ctk.CTkProgressBar(row, width=80, height=8, progress_color=BORDER_COLOR)
        indicator.set(0.0)
        indicator.pack(side="left", padx=10, pady=10)
        name_lbl = ctk.CTkLabel(row, text=name, font=FONT_BOLD, text_color=TEXT_COLOR)
        name_lbl.pack(side="left")
        ping_lbl = ctk.CTkLabel(row, text=f"{_T('latency')}: --ms", text_color=BORDER_COLOR, font=("Consolas", 10))
        ping_lbl.pack(side="right", padx=10)
        
        self.member_labels[member_id] = {"row": row, "indicator": indicator, "name_lbl": name_lbl, "ping_lbl": ping_lbl}

    def update_talking_state(self, member_id, rms):
        normalized_rms = min(rms / 4000.0, 1.0)
        ui_elems = self.member_labels.get(member_id)
        if ui_elems:
            if not ui_elems["indicator"].winfo_exists():
                return
            ui_elems["indicator"].set(normalized_rms)
            if normalized_rms > 0.05:
                ui_elems["indicator"].configure(progress_color=SUCCESS)
            else:
                ui_elems["indicator"].configure(progress_color=BORDER_COLOR)

    def update_status(self, member_id, status, toast_callback=None):
        ui_elems = self.member_labels.get(member_id)
        if status == "connected" and ui_elems:
            current_text = ui_elems["name_lbl"].cget("text")
            ui_elems["name_lbl"].configure(text=current_text.replace(_T('awaiting'), _T('established')), text_color=SUCCESS)
        elif status == "disconnected" and ui_elems:
            current_name = ui_elems["name_lbl"].cget("text")
            clean_name = current_name.replace(f" ({_T('established')})", "").replace("> ", "").replace(f"{_T('sys_root')} ", "")
            if toast_callback:
                toast_callback(f"⚠ {_T('disconnected')} {clean_name}")
            ui_elems["row"].destroy()
            del self.member_labels[member_id]

    def update_stats(self, member_id, ping):
        ui_elems = self.member_labels.get(member_id)
        if ui_elems:
            color = SUCCESS if ping < 100 else ("#F59E0B" if ping < 200 else DANGER)
            ui_elems["ping_lbl"].configure(text=f"{_T('latency')}: {ping}ms", text_color=color)

    def clear(self):
        for ui_elems in self.member_labels.values():
            if ui_elems["row"].winfo_exists():
                ui_elems["row"].destroy()
        self.member_labels.clear()

    def update_host_id(self, remote_id):
        if 'host' in self.member_labels:
            ui_elems = self.member_labels.pop('host')
            ui_elems["name_lbl"].configure(text=f"{_T('sys_root')} {remote_id} ({_T('established')})", text_color=SUCCESS)
            self.member_labels[remote_id] = ui_elems
