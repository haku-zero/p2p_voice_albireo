import customtkinter as ctk
from utils.i18n import get_text as _T
from ui.theme import *

class MemberView:
    def __init__(self, parent_frame, gov_api=None, local_id=None):
        self.frame = parent_frame
        self.gov_api = gov_api
        self.local_id = local_id
        self.member_labels = {}

    def add_member(self, member_id, name):
        if member_id in self.member_labels:
            ui_elems = self.member_labels[member_id]
            if ui_elems.get("name_lbl") and ui_elems["name_lbl"].winfo_exists():
                ui_elems["name_lbl"].configure(text=name)
            return
            
        row = ctk.CTkFrame(self.frame, fg_color="transparent", corner_radius=0, border_width=1, border_color=BORDER_COLOR)
        row.pack(fill="x", pady=5, padx=5)
        indicator = ctk.CTkProgressBar(row, width=80, height=8, corner_radius=0, progress_color=BORDER_COLOR)
        indicator.set(0.0)
        indicator.pack(side="left", padx=10, pady=10)
        name_lbl = ctk.CTkLabel(row, text=name, font=FONT_BOLD, text_color=TEXT_COLOR)
        name_lbl.pack(side="left")
        ping_lbl = ctk.CTkLabel(row, text=f"{_T('latency')}: --ms", text_color=BORDER_COLOR, font=("Consolas", 10))
        ping_lbl.pack(side="right", padx=10)
        
        def on_right_click(event):
            root = self.frame.winfo_toplevel()
            my_id = self.local_id or getattr(root, "local_id", None)
            if member_id == my_id: return
            
            gov_mgr = self.gov_api
            if not gov_mgr:
                engine = getattr(root, "engine", None)
                if engine:
                    gov_mgr = getattr(engine, "gov_mgr", None)
            if not gov_mgr: return

            menu = ctk.CTkToplevel(root)
            menu.overrideredirect(True)
            menu.geometry(f"+{event.x_root}+{event.y_root}")
            menu.configure(fg_color=BG_COLOR)
            menu.attributes("-topmost", True)
            menu_frame = ctk.CTkFrame(menu, fg_color=FRAME_COLOR, corner_radius=0, border_width=1, border_color=DANGER)
            menu_frame.pack(fill="both", expand=True)
            
            if gov_mgr.network_mode == 'archon' and gov_mgr.archon_id == my_id:
                ctk.CTkButton(menu_frame, text="[ EXECUTE_BANISHMENT ]", font=FONT_BOLD, text_color=DANGER, fg_color="transparent", hover_color=DANGER_HOV, corner_radius=0, command=lambda: [gov_mgr.issue_archon_banish(member_id), menu.destroy()]).pack(padx=5, pady=5)
                ctk.CTkButton(menu_frame, text="[ ASSIGN_HEIR ]", font=FONT_BOLD, text_color=SUCCESS, fg_color="transparent", hover_color=SUCCESS_HOV, corner_radius=0, command=lambda: [gov_mgr.assign_heir(member_id), menu.destroy()]).pack(padx=5, pady=5)
                if member_id in getattr(gov_mgr, "share_banned_list", []):
                    ctk.CTkButton(menu_frame, text="[ ALLOW_SHARE ]", font=FONT_BOLD, text_color=SECONDARY, fg_color="transparent", hover_color=SECONDARY_HOV, corner_radius=0, command=lambda: [gov_mgr.issue_share_permit(member_id, True), menu.destroy()]).pack(padx=5, pady=5)
                else:
                    ctk.CTkButton(menu_frame, text="[ REVOKE_SHARE ]", font=FONT_BOLD, text_color=SECONDARY, fg_color="transparent", hover_color=SECONDARY_HOV, corner_radius=0, command=lambda: [gov_mgr.issue_share_permit(member_id, False), menu.destroy()]).pack(padx=5, pady=5)
            else:
                ctk.CTkButton(menu_frame, text="[ PROPOSE_BANISHMENT ]", font=FONT_BOLD, text_color=WARNING, fg_color="transparent", hover_color=WARNING_HOV, corner_radius=0, command=lambda: [gov_mgr.issue_vote_kick(member_id), menu.destroy()]).pack(padx=5, pady=5)
            
            def close_menu(e):
                if menu.winfo_exists() and e.widget != menu and not str(e.widget).startswith(str(menu)):
                    menu.destroy()
            root.bind("<Button-1>", close_menu, add="+")
            
        row.bind("<Button-3>", on_right_click)
        name_lbl.bind("<Button-3>", on_right_click)
        
        self.member_labels[member_id] = {"row": row, "indicator": indicator, "name_lbl": name_lbl, "ping_lbl": ping_lbl}

    def update_callsign(self, member_id, callsign):
        ui_elems = self.member_labels.get(member_id)
        if ui_elems and ui_elems.get("name_lbl") and ui_elems["name_lbl"].winfo_exists():
            my_id = self.local_id
            if member_id == my_id:
                ui_elems["name_lbl"].configure(text=f"[ LOCAL_NODE ] {callsign}")
            else:
                ui_elems["name_lbl"].configure(text=f"> {callsign} ({_T('established')})")

    def update_talking_state(self, member_id, rms):
        normalized_rms = min(rms / 4000.0, 1.0)
        ui_elems = self.member_labels.get(member_id)
        if ui_elems:
            if not ui_elems["indicator"].winfo_exists():
                return
            ui_elems["indicator"].set(normalized_rms)
            if normalized_rms > 0.05:
                ui_elems["indicator"].configure(progress_color=SUCCESS)
                ui_elems["row"].configure(border_color=SUCCESS, border_width=2)
                ui_elems["name_lbl"].configure(text_color=SUCCESS)
            else:
                ui_elems["indicator"].configure(progress_color=BORDER_COLOR)
                ui_elems["row"].configure(border_color=BORDER_COLOR, border_width=1)
                ui_elems["name_lbl"].configure(text_color=TEXT_COLOR)

    def update_status(self, member_id, status, toast_callback=None):
        ui_elems = self.member_labels.get(member_id)
        if not ui_elems:
            return

        if status == "connected":
            current_text = ui_elems["name_lbl"].cget("text")
            clean_text = current_text.replace(_T('awaiting'), _T('established')).replace(" [RECONNECTING...]", f" ({_T('established')})")
            ui_elems["name_lbl"].configure(text=clean_text, text_color=SUCCESS)
            ui_elems["row"].configure(border_color=BORDER_COLOR)
        elif status == "ghost":
            current_text = ui_elems["name_lbl"].cget("text")
            ghost_text = current_text.replace(f" ({_T('established')})", "").replace(" [RECONNECTING...]", "") + " [RECONNECTING...]"
            ui_elems["name_lbl"].configure(text=ghost_text, text_color=TEXT_MUTED)
            ui_elems["row"].configure(border_color=WARNING)
        elif status == "disconnected":
            current_name = ui_elems["name_lbl"].cget("text")
            clean_name = current_name.replace(f" ({_T('established')})", "").replace(" [RECONNECTING...]", "").replace("> ", "").replace(f"{_T('sys_root')} ", "")
            if toast_callback:
                toast_callback(f"⚠ {_T('disconnected')} {clean_name}")
            ui_elems["row"].destroy()
            del self.member_labels[member_id]

    def update_stats(self, member_id, ping):
        ui_elems = self.member_labels.get(member_id)
        if ui_elems:
            color = SUCCESS if ping < 100 else (WARNING if ping < 200 else DANGER)
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
