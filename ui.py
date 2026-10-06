import customtkinter as ctk
import asyncio
import os
import settings
from i18n import get_text as _T

# Cyberpunk / Tech Theme Constants
BG_COLOR = "#090C15"          
FRAME_COLOR = "#111726"       
BORDER_COLOR = "#1E293B"      
PRIMARY = "#00F0FF"           
PRIMARY_HOV = "#005566"       
SECONDARY = "#A23BFF"         
SECONDARY_HOV = "#441177"     
SUCCESS = "#00FF9D"           
DANGER = "#FF003C"            
DANGER_HOV = "#550011"        
TEXT_COLOR = "#E0E7FF"        
FONT_MAIN = ("Consolas", 12)
FONT_BOLD = ("Consolas", 12, "bold")
FONT_TITLE = ("Consolas", 14, "bold")

class UIController:
    def __init__(self, app_root, webrtc_engine, audio_inputs, audio_outputs, local_mic, playback_mgr, loop):
        self.root = app_root
        self.engine = webrtc_engine
        self.inputs_map = audio_inputs
        self.outputs_map = audio_outputs
        self.local_mic = local_mic
        self.playback_mgr = playback_mgr
        self.loop = loop
        self.member_labels = {}
        
        self.chat_window = None
        self.chat_box = None
        self.chat_btn = None

    def copy_to_clipboard(self, text, btn):
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.root.update()
        btn.configure(text=_T("copied"), fg_color=SUCCESS, text_color=BG_COLOR)
        self.root.after(2000, lambda: btn.configure(text=_T("copy_key"), fg_color="transparent", text_color=PRIMARY))

    def build_top_bar(self):
        top_container = ctk.CTkFrame(self.root, fg_color="transparent")
        top_container.pack(fill="x", padx=10, pady=5)
        
        row0 = ctk.CTkFrame(top_container, fg_color="transparent")
        row0.pack(fill="x", pady=(0, 5))
        ctk.CTkButton(row0, text=_T("exit_link"), width=120, font=FONT_BOLD, fg_color="transparent", border_width=1, border_color=DANGER, text_color=DANGER, hover_color=DANGER_HOV, command=self.exit_room).pack(side="left")
        
        row1 = ctk.CTkFrame(top_container, fg_color="transparent")
        row1.pack(fill="x", pady=2)
        
        ctk.CTkLabel(row1, text=_T("audio_in"), font=FONT_MAIN, text_color=TEXT_COLOR).pack(side="left", padx=2)
        self.in_combo = ctk.CTkComboBox(row1, values=list(self.inputs_map.keys()), command=self.change_in_device, width=220, font=FONT_MAIN, fg_color=FRAME_COLOR, border_color=BORDER_COLOR, button_color=BORDER_COLOR, button_hover_color=PRIMARY, text_color=PRIMARY)
        self.in_combo.pack(side="left", padx=5)
        
        ctk.CTkLabel(row1, text=_T("audio_out"), font=FONT_MAIN, text_color=TEXT_COLOR).pack(side="left", padx=(15, 2))
        self.out_combo = ctk.CTkComboBox(row1, values=list(self.outputs_map.keys()), command=self.change_out_device, width=220, font=FONT_MAIN, fg_color=FRAME_COLOR, border_color=BORDER_COLOR, button_color=BORDER_COLOR, button_hover_color=PRIMARY, text_color=PRIMARY)
        self.out_combo.pack(side="left", padx=5)
        
        cfg = settings.load_config()
        saved_in = cfg.get("in_device")
        in_names = list(self.inputs_map.keys())
        if saved_in not in in_names and in_names:
            saved_in = in_names[0]
        if saved_in:
            self.in_combo.set(saved_in)
            self.change_in_device(saved_in)
            
        saved_out = cfg.get("out_device")
        out_names = list(self.outputs_map.keys())
        if saved_out not in out_names and out_names:
            saved_out = out_names[0]
        if saved_out:
            self.out_combo.set(saved_out)
            self.change_out_device(saved_out)
            
        settings.save_config("in_device", saved_in)
        settings.save_config("out_device", saved_out)
        
        row2 = ctk.CTkFrame(top_container, fg_color="transparent")
        row2.pack(fill="x", pady=8)
        
        self.mic_btn = ctk.CTkButton(row2, text=_T("mic_on"), font=FONT_BOLD, width=100, fg_color="transparent", border_width=1, border_color=PRIMARY, text_color=PRIMARY, hover_color=PRIMARY_HOV, command=self.toggle_mic)
        self.mic_btn.pack(side="left", padx=2)
        
        self.mic_vol_slider = ctk.CTkSlider(row2, from_=0, to=1.0, width=80, command=self.change_mic_volume, button_color=PRIMARY, button_hover_color=SUCCESS, progress_color=PRIMARY)
        saved_mic_vol = settings.load_config().get("mic_vol", 1.0)
        self.mic_vol_slider.set(saved_mic_vol)
        self.local_mic.volume = saved_mic_vol
        settings.save_config("mic_vol", saved_mic_vol)
        self.mic_vol_slider.pack(side="left", padx=5)
        
        self.mic_mode_menu = ctk.CTkOptionMenu(row2, values=[_T("open_mic"), _T("ptt")], font=FONT_MAIN, command=self.change_mic_mode, width=160, fg_color=FRAME_COLOR, button_color=PRIMARY, button_hover_color=PRIMARY_HOV, text_color=PRIMARY)
        saved_mic_mode = settings.load_config().get("mic_mode", _T("open_mic"))
        self.mic_mode_menu.set(saved_mic_mode)
        self.mic_mode_menu.pack(side="left", padx=5)
        
        self.ptt_btn = ctk.CTkButton(row2, text=_T("ptt_stdby"), font=FONT_BOLD, width=120, fg_color="transparent", border_width=1, border_color=BORDER_COLOR, text_color=BORDER_COLOR, state="disabled")
        self.ptt_btn.pack(side="left", padx=5)
        self.ptt_btn.bind("<ButtonPress-1>", self.ptt_press)
        self.ptt_btn.bind("<ButtonRelease-1>", self.ptt_release)
        
        self.change_mic_mode(saved_mic_mode)
        
        self.speaker_btn = ctk.CTkButton(row2, text=_T("spk_on"), font=FONT_BOLD, width=100, fg_color="transparent", border_width=1, border_color=SECONDARY, text_color=SECONDARY, hover_color=SECONDARY_HOV, command=self.toggle_speaker)
        self.speaker_btn.pack(side="left", padx=(15, 2))
        
        self.vol_slider = ctk.CTkSlider(row2, from_=0, to=1.0, width=100, command=self.change_volume, button_color=SECONDARY, button_hover_color=SUCCESS, progress_color=SECONDARY)
        saved_spk_vol = settings.load_config().get("speaker_vol", 0.1)
        self.vol_slider.set(saved_spk_vol)
        self.playback_mgr.volume = saved_spk_vol
        settings.save_config("speaker_vol", saved_spk_vol)
        self.vol_slider.bind("<ButtonRelease-1>", lambda e: self.playback_mgr.play_beep())
        self.vol_slider.pack(side="left", padx=5)
        
        self.chat_btn = ctk.CTkButton(row2, text=_T("chat"), font=FONT_BOLD, width=120, fg_color="transparent", border_width=1, border_color=PRIMARY, text_color=PRIMARY, hover_color=PRIMARY_HOV, command=self.open_chat_window)
        self.chat_btn.pack(side="right", padx=10)
        
        self.file_btn = ctk.CTkButton(row2, text=_T("file"), font=FONT_BOLD, width=120, fg_color="transparent", border_width=1, border_color="#F59E0B", text_color="#F59E0B", hover_color="#B45309", command=self.send_file_dialog)
        self.file_btn.pack(side="right", padx=5)

    def change_mic_mode(self, mode):
        settings.save_config("mic_mode", mode)
        if _T("ptt") in mode or "PUSH" in mode or "按住" in mode:
            self.ptt_btn.configure(state="normal", text=_T("hold_tx"), border_color=PRIMARY, text_color=PRIMARY)
            self.mic_btn.configure(state="disabled", text=_T("mic_lock"), border_color=BORDER_COLOR, text_color=BORDER_COLOR)
            self.local_mic.muted = True
        else:
            self.ptt_btn.configure(state="disabled", text=_T("ptt_stdby"), border_color=BORDER_COLOR, text_color=BORDER_COLOR)
            self.mic_btn.configure(state="normal", text=_T("mic_on"), border_color=PRIMARY, text_color=PRIMARY)
            self.local_mic.muted = False

    def ptt_press(self, event):
        if self.ptt_btn.cget("state") == "normal":
            self.local_mic.muted = False
            self.ptt_btn.configure(fg_color=SUCCESS, text_color=BG_COLOR, text=_T("tx_active"))

    def ptt_release(self, event):
        if self.ptt_btn.cget("state") == "normal":
            self.local_mic.muted = True
            self.ptt_btn.configure(fg_color="transparent", text_color=PRIMARY, text=_T("hold_tx"))

    def toggle_mic(self):
        self.local_mic.muted = not self.local_mic.muted
        if self.local_mic.muted:
            self.mic_btn.configure(text=_T("mic_muted"), border_color=DANGER, text_color=DANGER)
        else:
            self.mic_btn.configure(text=_T("mic_on"), border_color=PRIMARY, text_color=PRIMARY)

    def change_in_device(self, val):
        idx = self.inputs_map.get(val)
        if idx is not None:
            self.local_mic.change_device(idx)
            settings.save_config("in_device", val)
        
    def change_out_device(self, val):
        idx = self.outputs_map.get(val)
        if idx is not None:
            self.playback_mgr.change_device(idx)
            settings.save_config("out_device", val)

    def change_mic_volume(self, value):
        val = float(value)
        self.local_mic.volume = val
        settings.save_config("mic_vol", val)

    def toggle_speaker(self):
        self.playback_mgr.muted = not self.playback_mgr.muted
        if self.playback_mgr.muted:
            self.speaker_btn.configure(text=_T("spk_muted"), border_color=DANGER, text_color=DANGER)
        else:
            self.speaker_btn.configure(text=_T("spk_on"), border_color=SECONDARY, text_color=SECONDARY)

    def change_volume(self, value):
        val = float(value)
        self.playback_mgr.volume = val
        settings.save_config("speaker_vol", val)

    def open_chat_window(self):
        self.chat_btn.configure(text=_T("chat"), border_color=PRIMARY, text_color=PRIMARY)
        
        if self.chat_window is None or not self.chat_window.winfo_exists():
            self.chat_window = ctk.CTkToplevel(self.root)
            self.chat_window.title("SECURE_CHANNEL")
            self.chat_window.geometry("450x550")
            self.chat_window.transient(self.root)
            self.chat_window.configure(fg_color=BG_COLOR)
            
            self.chat_box = ctk.CTkTextbox(self.chat_window, state="disabled", fg_color=FRAME_COLOR, border_color=BORDER_COLOR, border_width=1, font=FONT_MAIN, text_color=TEXT_COLOR)
            self.chat_box.pack(fill="both", expand=True, padx=10, pady=10)
            
            input_frame = ctk.CTkFrame(self.chat_window, fg_color="transparent")
            input_frame.pack(fill="x", padx=10, pady=(0, 10))
            
            self.chat_entry = ctk.CTkEntry(input_frame, placeholder_text=">", font=FONT_MAIN, fg_color=BG_COLOR, border_color=PRIMARY, text_color=PRIMARY)
            self.chat_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
            self.chat_entry.bind("<Return>", lambda e: self.send_chat_msg())
            
            ctk.CTkButton(input_frame, text="[ TX ]", font=FONT_BOLD, width=60, fg_color="transparent", border_width=1, border_color=SUCCESS, text_color=SUCCESS, hover_color="#004433", command=self.send_chat_msg).pack(side="right")
            
            self.chat_window.protocol("WM_DELETE_WINDOW", self.hide_chat_window)
        else:
            self.chat_window.deiconify()
            self.chat_window.focus()

    def hide_chat_window(self):
        self.chat_window.withdraw()

    def send_chat_msg(self):
        msg = self.chat_entry.get().strip()
        if not msg: return
        self.chat_entry.delete(0, "end")
        self.append_chat(f"[{self.root.local_id}]> {msg}")
        self.engine.send_chat(msg)

    def send_file_dialog(self):
        from tkinter import filedialog
        filepath = filedialog.askopenfilename()
        if filepath:
            self.engine.send_file(filepath)
            self.append_chat(f"[{self.root.local_id}]> {_T('uploading')} -> {os.path.basename(filepath)}")

    def update_file_progress(self, member_id, progress):
        pct = int(progress * 100)
        self.file_btn.configure(text=f"[{pct}%]", border_color=SUCCESS, text_color=SUCCESS)
        if pct >= 100:
            self.root.after(1000, lambda: self.file_btn.configure(text=_T("file"), border_color="#F59E0B", text_color="#F59E0B"))

    def append_chat(self, text):
        if self.chat_window is None or not self.chat_window.winfo_exists():
            self.open_chat_window()
            self.chat_window.withdraw()
            
        self.chat_box.configure(state="normal")
        self.chat_box.insert("end", text + "\n")
        self.chat_box.see("end")
        self.chat_box.configure(state="disabled")
        
        if not self.chat_window.winfo_viewable():
            self.chat_btn.configure(text=_T("incoming_msg"), border_color=SUCCESS, text_color=SUCCESS)

    def add_member_ui(self, parent_frame, member_id, name):
        row = ctk.CTkFrame(parent_frame, fg_color="transparent", border_width=1, border_color=BORDER_COLOR)
        row.pack(fill="x", pady=5, padx=5)
        indicator = ctk.CTkProgressBar(row, width=80, height=8, progress_color=BORDER_COLOR)
        indicator.set(0.0)
        indicator.pack(side="left", padx=10, pady=10)
        name_lbl = ctk.CTkLabel(row, text=name, font=FONT_BOLD, text_color=TEXT_COLOR)
        name_lbl.pack(side="left")
        ping_lbl = ctk.CTkLabel(row, text=f"{_T('latency')}: --ms", text_color=BORDER_COLOR, font=("Consolas", 10))
        ping_lbl.pack(side="right", padx=10)
        
        self.member_labels[member_id] = {"indicator": indicator, "name_lbl": name_lbl, "ping_lbl": ping_lbl}

    def update_talking_state(self, member_id, rms):
        normalized_rms = min(rms / 4000.0, 1.0)
        ui_elems = self.member_labels.get(member_id)
        if ui_elems:
            ui_elems["indicator"].set(normalized_rms)
            if normalized_rms > 0.05:
                ui_elems["indicator"].configure(progress_color=SUCCESS)
            else:
                ui_elems["indicator"].configure(progress_color=BORDER_COLOR)

    def update_status(self, member_id, status):
        ui_elems = self.member_labels.get(member_id)
        if status == "connected" and ui_elems:
            current_text = ui_elems["name_lbl"].cget("text")
            ui_elems["name_lbl"].configure(text=current_text.replace(_T('awaiting'), _T('established')), text_color=SUCCESS)

    def update_stats(self, member_id, ping):
        ui_elems = self.member_labels.get(member_id)
        if ui_elems:
            color = SUCCESS if ping < 100 else ("#F59E0B" if ping < 200 else DANGER)
            ui_elems["ping_lbl"].configure(text=f"{_T('latency')}: {ping}ms", text_color=color)

    def build_host_ui(self, work_frame):
        main_area = ctk.CTkFrame(work_frame, fg_color="transparent")
        main_area.pack(side="left", fill="both", expand=True)
        
        top = ctk.CTkFrame(main_area, fg_color="transparent")
        top.pack(fill="x", padx=20, pady=10)
        ctk.CTkButton(top, text=_T("invite"), font=FONT_BOLD, fg_color="transparent", border_width=1, border_color=PRIMARY, text_color=PRIMARY, hover_color=PRIMARY_HOV, command=self.open_host_modal).pack(side="left")
                      
        self.members_frame = ctk.CTkScrollableFrame(main_area, label_text=_T("topology"), label_font=FONT_TITLE, fg_color=FRAME_COLOR, label_fg_color=BG_COLOR, label_text_color=PRIMARY, border_width=1, border_color=BORDER_COLOR)
        self.members_frame.pack(fill="both", expand=True, padx=20, pady=10)
        self.add_member_ui(self.members_frame, self.root.local_id, f"{_T('sys_root')} {self.root.local_id}")

    def open_host_modal(self):
        modal = ctk.CTkToplevel(self.root)
        modal.title(_T("wizard_host_title"))
        modal.geometry("550x500")
        modal.transient(self.root)
        modal.grab_set()
        modal.configure(fg_color=BG_COLOR)
        
        ctk.CTkLabel(modal, text=_T("phase1_host"), font=FONT_BOLD, text_color=PRIMARY).pack(pady=(15, 0), anchor="w", padx=20)
        offer_box = ctk.CTkTextbox(modal, height=80, fg_color=FRAME_COLOR, border_color=PRIMARY, border_width=1, text_color=TEXT_COLOR, font=FONT_MAIN)
        offer_box.pack(fill="x", padx=20, pady=5)
        
        process_btn = ctk.CTkButton(modal, text=_T("compute_ans"), font=FONT_BOLD, fg_color="transparent", border_width=1, border_color=SECONDARY, text_color=SECONDARY, hover_color=SECONDARY_HOV)
        process_btn.pack(pady=15)
        
        ctk.CTkLabel(modal, text=_T("phase2_host"), font=FONT_BOLD, text_color=PRIMARY).pack(pady=(10, 0), anchor="w", padx=20)
        answer_box = ctk.CTkTextbox(modal, height=80, fg_color=FRAME_COLOR, border_color=SECONDARY, border_width=1, text_color=TEXT_COLOR, font=FONT_MAIN)
        answer_box.pack(fill="x", padx=20, pady=5)
        
        copy_ans_btn = ctk.CTkButton(modal, text=_T("copy_key"), width=120, font=FONT_BOLD, fg_color="transparent", border_width=1, border_color=PRIMARY, text_color=PRIMARY, state="disabled")
        copy_ans_btn.pack(pady=5)
        
        status_lbl = ctk.CTkLabel(modal, text=_T("await_input"), font=FONT_MAIN, text_color=BORDER_COLOR)
        status_lbl.pack(pady=10)
        
        def process():
            offer_str = offer_box.get("1.0", "end").strip()
            if not offer_str: return
            process_btn.configure(state="disabled")
            status_lbl.configure(text=_T("computing_keys"), text_color=SECONDARY)
            
            def done(ans_str, remote_id, err):
                if err:
                    status_lbl.configure(text=f"ERROR: {ans_str}", text_color=DANGER)
                    process_btn.configure(state="normal")
                    return
                answer_box.delete("1.0", "end")
                answer_box.insert("end", ans_str)
                copy_ans_btn.configure(state="normal", command=lambda: self.copy_to_clipboard(ans_str, copy_ans_btn))
                status_lbl.configure(text=f"{_T('link_est')} [{remote_id}].", text_color=SUCCESS)
                self.add_member_ui(self.members_frame, remote_id, f"> {remote_id} ({_T('established')})")
                
            asyncio.run_coroutine_threadsafe(self.engine.host_accept_offer(offer_str, self.root.local_id, done), self.loop)
            
        process_btn.configure(command=process)

    def build_client_ui(self, work_frame):
        main_area = ctk.CTkFrame(work_frame, fg_color="transparent")
        main_area.pack(side="left", fill="both", expand=True)
        
        self.members_frame = ctk.CTkScrollableFrame(main_area, label_text=_T("topology"), label_font=FONT_TITLE, fg_color=FRAME_COLOR, label_fg_color=BG_COLOR, label_text_color=PRIMARY, border_width=1, border_color=BORDER_COLOR)
        self.members_frame.pack(fill="both", expand=True, padx=20, pady=10)
        
        self.add_member_ui(self.members_frame, self.root.local_id, f"> {self.root.local_id}")
        self.add_member_ui(self.members_frame, "host", f"{_T('sys_root')} ({_T('awaiting')})")
        
        ctk.CTkButton(main_area, text=_T("init_seq"), font=FONT_TITLE, height=45, fg_color="transparent", border_width=1, border_color=SUCCESS, text_color=SUCCESS, hover_color="#004433", command=self.open_client_modal).pack(pady=10)

    def open_client_modal(self):
        modal = ctk.CTkToplevel(self.root)
        modal.title(_T("wizard_client_title"))
        modal.geometry("550x500")
        modal.transient(self.root)
        modal.grab_set()
        modal.configure(fg_color=BG_COLOR)
        
        gen_btn = ctk.CTkButton(modal, text=_T("phase1_client"), font=FONT_BOLD, fg_color="transparent", border_width=1, border_color=SECONDARY, text_color=SECONDARY, hover_color=SECONDARY_HOV)
        gen_btn.pack(pady=15)
        
        offer_box = ctk.CTkTextbox(modal, height=60, fg_color=FRAME_COLOR, border_color=SECONDARY, border_width=1, text_color=TEXT_COLOR, font=FONT_MAIN)
        offer_box.pack(fill="x", padx=20, pady=5)
        
        copy_offer_btn = ctk.CTkButton(modal, text=_T("copy_key"), width=120, font=FONT_BOLD, fg_color="transparent", border_width=1, border_color=PRIMARY, text_color=PRIMARY, state="disabled")
        copy_offer_btn.pack(pady=5)
        
        ctk.CTkLabel(modal, text=_T("phase2_client"), font=FONT_BOLD, text_color=PRIMARY).pack(pady=(15,0), anchor="w", padx=20)
        answer_box = ctk.CTkTextbox(modal, height=60, fg_color=FRAME_COLOR, border_color=PRIMARY, border_width=1, text_color=TEXT_COLOR, font=FONT_MAIN)
        answer_box.pack(fill="x", padx=20, pady=5)
        
        conn_btn = ctk.CTkButton(modal, text=_T("finalize"), font=FONT_BOLD, fg_color="transparent", border_width=1, border_color=SUCCESS, text_color=SUCCESS, hover_color="#004433")
        conn_btn.pack(pady=20)
        
        status_lbl = ctk.CTkLabel(modal, text=_T("await_input"), font=FONT_MAIN, text_color=BORDER_COLOR)
        status_lbl.pack()
        
        def gen():
            gen_btn.configure(state="disabled")
            status_lbl.configure(text=_T("gen_keys"), text_color=SECONDARY)
            def done(offer_str, err):
                if err:
                    status_lbl.configure(text=f"ERROR: {offer_str}", text_color=DANGER)
                    gen_btn.configure(state="normal")
                    return
                offer_box.delete("1.0", "end")
                offer_box.insert("end", offer_str)
                copy_offer_btn.configure(state="normal", command=lambda: self.copy_to_clipboard(offer_str, copy_offer_btn))
                status_lbl.configure(text=_T("offer_ready"), text_color=SUCCESS)
            asyncio.run_coroutine_threadsafe(self.engine.client_generate_offer(self.root.local_id, done), self.loop)
            
        def conn():
            ans_str = answer_box.get("1.0", "end").strip()
            if not ans_str: return
            def done(remote_id, err_msg):
                if not err_msg:
                    self.root.after(0, lambda: self.update_host_id(remote_id))
                    self.root.after(0, lambda: modal.destroy())
                else:
                    self.root.after(0, lambda: status_lbl.configure(text=f"ERROR: {err_msg}", text_color=DANGER))
            asyncio.run_coroutine_threadsafe(self.engine.client_accept_answer(ans_str, done), self.loop)

        gen_btn.configure(command=gen)
        conn_btn.configure(command=conn)

    def update_host_id(self, remote_id):
        if 'host' in self.member_labels:
            ui_elems = self.member_labels.pop('host')
            ui_elems["name_lbl"].configure(text=f"{_T('sys_root')} {remote_id} ({_T('established')})", text_color=SUCCESS)
            self.member_labels[remote_id] = ui_elems

    def exit_room(self):
        self.engine.reset()
        if self.chat_window and self.chat_window.winfo_exists():
            self.chat_window.destroy()
            self.chat_window = None
        self.member_labels.clear()
        self.root.show_role_selection()
