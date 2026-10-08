import customtkinter as ctk
from utils.i18n import get_text as _T
from utils import config
from ui.theme import *
from ui.chat_view import ChatWindow
from ui.member_view import MemberView
from ui.modals import HostWizard, ClientWizard
from ui.toast import ToastManager
from ui.video_view import VideoViewManager

class UIManager:
    def __init__(self, app_root, webrtc_engine, audio_inputs, audio_outputs, local_mic, playback_mgr, loop):
        self.root = app_root
        self.engine = webrtc_engine
        self.inputs_map = audio_inputs
        self.outputs_map = audio_outputs
        self.local_mic = local_mic
        self.playback_mgr = playback_mgr
        self.loop = loop
        
        self.chat_view = ChatWindow(self.root, self.engine, self._on_chat_hidden)
        self.member_view = None
        self.toast_mgr = ToastManager(self.root)
        self.video_mgr = VideoViewManager(self.root, self.engine)

        from utils.events import event_bus
        event_bus.on("toast", lambda msg: self.root.after(0, self.toast_mgr.show_toast, msg))
        event_bus.on("talking", lambda mid, rms: self.root.after(0, self.update_talking_state, mid, rms))
        event_bus.on("local_mic_level", lambda rms: self.root.after(0, self.update_talking_state, self.root.local_id, rms))
        event_bus.on("status", lambda mid, st: self.root.after(0, self.update_status, mid, st))
        event_bus.on("stats", lambda mid, ping: self.root.after(0, self.update_stats, mid, ping))
        event_bus.on("chat_message", lambda mid, msg: self.root.after(0, self.append_chat, msg, False, None, mid))
        event_bus.on("file_incoming", lambda mid, fn, sz, fid: self.root.after(0, self.add_file_transfer, mid, fn, sz, fid))
        event_bus.on("file_done", lambda mid, fn, fp, fid: self.root.after(0, self.complete_file_transfer, mid, fn, fp, fid))
        event_bus.on("file_progress", lambda mid, prog, fid: self.root.after(0, self.update_file_progress, fid, prog))
        event_bus.on("vote_requested", lambda target, vid: self.root.after(0, self.show_vote_modal, target, vid))
        event_bus.on("election_requested", lambda rnd, cand: self.root.after(0, self.show_election_modal, rnd, cand))
        event_bus.on("video_frame", lambda pid, arr: self.root.after(0, self.video_mgr.update_frame, pid, arr))

    def _on_chat_hidden(self):
        # Callback when chat is hidden/closed
        pass

    def build_top_bar(self):
        top_container = ctk.CTkFrame(self.root, fg_color="transparent")
        top_container.pack(fill="x", padx=10, pady=5)
        
        row0 = ctk.CTkFrame(top_container, fg_color="transparent")
        row0.pack(fill="x", pady=(0, 5))
        ctk.CTkButton(row0, text=_T("exit_link"), width=120, font=FONT_BOLD, corner_radius=0, fg_color="transparent", border_width=1, border_color=DANGER, text_color=DANGER, hover_color=DANGER_HOV, command=self.exit_room).pack(side="left")
        
        row1 = ctk.CTkFrame(top_container, fg_color="transparent")
        row1.pack(fill="x", pady=2)
        
        ctk.CTkLabel(row1, text=_T("audio_in"), font=FONT_MAIN, text_color=TEXT_COLOR).pack(side="left", padx=2)
        self.in_combo = ctk.CTkComboBox(row1, values=list(self.inputs_map.keys()), command=self.change_in_device, width=220, font=FONT_MAIN, fg_color=FRAME_COLOR, border_color=BORDER_COLOR, button_color=BORDER_COLOR, button_hover_color=PRIMARY, text_color=PRIMARY)
        self.in_combo.pack(side="left", padx=5)
        
        ctk.CTkLabel(row1, text=_T("audio_out"), font=FONT_MAIN, text_color=TEXT_COLOR).pack(side="left", padx=(15, 2))
        self.out_combo = ctk.CTkComboBox(row1, values=list(self.outputs_map.keys()), command=self.change_out_device, width=220, font=FONT_MAIN, fg_color=FRAME_COLOR, border_color=BORDER_COLOR, button_color=BORDER_COLOR, button_hover_color=PRIMARY, text_color=PRIMARY)
        self.out_combo.pack(side="left", padx=5)
        
        cfg = config.load_config()
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
            
        config.save_config("in_device", saved_in)
        config.save_config("out_device", saved_out)
        
        row2 = ctk.CTkFrame(top_container, fg_color="transparent")
        row2.pack(fill="x", pady=8)
        
        self.mic_btn = ctk.CTkButton(row2, text=_T("mic_on"), font=FONT_BOLD, width=100, corner_radius=0, fg_color="transparent", border_width=1, border_color=PRIMARY, text_color=PRIMARY, hover_color=PRIMARY_HOV, command=self.toggle_mic)
        self.mic_btn.pack(side="left", padx=2)
        
        self.mic_vol_slider = ctk.CTkSlider(row2, from_=0, to=1.0, width=80, command=self.change_mic_volume, button_color=PRIMARY, button_hover_color=SUCCESS, progress_color=PRIMARY)
        saved_mic_vol = config.load_config().get("mic_vol", 1.0)
        self.mic_vol_slider.set(saved_mic_vol)
        self.local_mic.volume = saved_mic_vol
        config.save_config("mic_vol", saved_mic_vol)
        self.mic_vol_slider.pack(side="left", padx=5)
        
        self.mic_mode_menu = ctk.CTkOptionMenu(row2, values=[_T("open_mic"), _T("ptt")], font=FONT_MAIN, command=self.change_mic_mode, width=160, fg_color=FRAME_COLOR, button_color=PRIMARY, button_hover_color=PRIMARY_HOV, text_color=PRIMARY)
        saved_mic_mode = config.load_config().get("mic_mode", _T("open_mic"))
        self.mic_mode_menu.set(saved_mic_mode)
        self.mic_mode_menu.pack(side="left", padx=5)
        
        self.ptt_btn = ctk.CTkButton(row2, text=_T("ptt_stdby"), font=FONT_BOLD, width=120, corner_radius=0, fg_color="transparent", border_width=1, border_color=BORDER_COLOR, text_color=BORDER_COLOR, state="disabled")
        self.ptt_btn.pack(side="left", padx=5)
        self.ptt_btn.bind("<ButtonPress-1>", self.ptt_press)
        self.ptt_btn.bind("<ButtonRelease-1>", self.ptt_release)
        
        self.change_mic_mode(saved_mic_mode)
        
        self.speaker_btn = ctk.CTkButton(row2, text=_T("spk_on"), font=FONT_BOLD, width=100, corner_radius=0, fg_color="transparent", border_width=1, border_color=SECONDARY, text_color=SECONDARY, hover_color=SECONDARY_HOV, command=self.toggle_speaker)
        self.speaker_btn.pack(side="left", padx=(15, 2))
        
        self.vol_slider = ctk.CTkSlider(row2, from_=0, to=1.0, width=100, command=self.change_volume, button_color=SECONDARY, button_hover_color=SUCCESS, progress_color=SECONDARY)
        saved_spk_vol = config.load_config().get("speaker_vol", 0.1)
        self.vol_slider.set(saved_spk_vol)
        self.playback_mgr.volume = saved_spk_vol
        config.save_config("speaker_vol", saved_spk_vol)
        self.vol_slider.bind("<ButtonRelease-1>", lambda e: self.playback_mgr.play_beep())
        self.vol_slider.pack(side="left", padx=5)
        
        self.chat_btn = ctk.CTkButton(row2, text=_T("chat"), font=FONT_BOLD, width=120, corner_radius=0, fg_color="transparent", border_width=1, border_color=PRIMARY, text_color=PRIMARY, hover_color=PRIMARY_HOV, command=self.chat_view.open)
        self.chat_btn.pack(side="right", padx=10)
        self.chat_view.chat_btn = self.chat_btn

    def change_mic_mode(self, mode):
        config.save_config("mic_mode", mode)
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
            config.save_config("in_device", val)
        
    def change_out_device(self, val):
        idx = self.outputs_map.get(val)
        if idx is not None:
            self.playback_mgr.change_device(idx)
            config.save_config("out_device", val)

    def change_mic_volume(self, value):
        val = float(value)
        self.local_mic.volume = val
        config.save_config("mic_vol", val)

    def toggle_speaker(self):
        self.playback_mgr.muted = not self.playback_mgr.muted
        if self.playback_mgr.muted:
            self.speaker_btn.configure(text=_T("spk_muted"), border_color=DANGER, text_color=DANGER)
        else:
            self.speaker_btn.configure(text=_T("spk_on"), border_color=SECONDARY, text_color=SECONDARY)

    def change_volume(self, value):
        val = float(value)
        self.playback_mgr.volume = val
        config.save_config("speaker_vol", val)

    def show_toast(self, message, timeout_ms=5000):
        toast = ctk.CTkFrame(self.root, fg_color=FRAME_COLOR, border_color=PRIMARY, border_width=2, corner_radius=0)
        lbl = ctk.CTkLabel(toast, text=message, font=FONT_BOLD, text_color=SUCCESS)
        lbl.pack(padx=30, pady=12)
        
        slot = len(self.active_toasts)
        rely = 0.12 + 0.06 * slot
        toast.place(relx=0.5, rely=rely, anchor="center")
        self.active_toasts.append(toast)
        
        def remove_toast():
            if toast.winfo_exists():
                toast.destroy()
            if toast in self.active_toasts:
                self.active_toasts.remove(toast)
        self.root.after(timeout_ms, remove_toast)

    def build_node_ui(self, work_frame):
        self.current_role = 'node'
        main_area = ctk.CTkFrame(work_frame, fg_color="transparent")
        main_area.pack(side="left", fill="both", expand=True)
        
        top = ctk.CTkFrame(main_area, fg_color="transparent")
        top.pack(fill="x", padx=20, pady=10)
        
        def on_complete(remote_id):
            if self.member_view:
                csign = self.engine.callsign_map.get(remote_id, remote_id[:8])
                self.member_view.add_member(remote_id, f"> {csign} ({_T('established')})")
                
        host_wizard = HostWizard(self.root, self.engine, self.loop, on_complete)
        ctk.CTkButton(top, text=_T("invite"), font=FONT_BOLD, corner_radius=0, fg_color="transparent", border_width=1, border_color=PRIMARY, text_color=PRIMARY, hover_color=PRIMARY_HOV, command=host_wizard.open).pack(side="left", padx=(0, 10))
        
        client_wizard = ClientWizard(self.root, self.engine, self.loop, on_complete)
        ctk.CTkButton(top, text=_T("init_seq"), font=FONT_BOLD, corner_radius=0, fg_color="transparent", border_width=1, border_color=SUCCESS, text_color=SUCCESS, hover_color="#004433", command=client_wizard.open).pack(side="left")
                      
        self.share_btn = ctk.CTkButton(top, text="[ SHARE_SCREEN ]", font=FONT_BOLD, corner_radius=0, fg_color="transparent", border_width=1, border_color="#A855F7", text_color="#A855F7", hover_color="#7E22CE", command=self.toggle_share)
        self.share_btn.pack(side="left", padx=10)
        
        members_frame = ctk.CTkScrollableFrame(main_area, label_text=_T("topology"), label_font=FONT_TITLE, fg_color=FRAME_COLOR, label_fg_color=BG_COLOR, label_text_color=PRIMARY, border_width=1, border_color=BORDER_COLOR)
        members_frame.pack(fill="both", expand=True, padx=20, pady=10)
        
        self.member_view = MemberView(members_frame)
        self.member_view.add_member(self.root.local_id, f"[ LOCAL_NODE ] {self.engine.callsign}")

    def toggle_share(self):
        if self.engine.local_id in self.engine.gov_mgr.share_banned_list:
            self.toast_mgr.show_toast("Permission Denied: Screen Share revoked by Archon.")
            return
            
        is_sharing = self.engine.toggle_screen_share()
        if is_sharing:
            self.share_btn.configure(text="[ STOP_SHARE ]", border_color=DANGER, text_color=DANGER, hover_color="#7F1D1D")
        else:
            self.share_btn.configure(text="[ SHARE_SCREEN ]", border_color="#A855F7", text_color="#A855F7", hover_color="#7E22CE")

    def exit_room(self):
        self.engine.reset()
        self.chat_view.destroy()
        if self.member_view:
            self.member_view.clear()
        self.root.show_id_selection()

    def reset_room(self):
        if not self.member_view:
            return
        pass

    def update_talking_state(self, member_id, rms):
        if self.member_view:
            self.member_view.update_talking_state(member_id, rms)

    def update_status(self, member_id, status):
        if self.member_view:
            self.member_view.update_status(member_id, status, self.toast_mgr.show_toast)
            if status == "disconnected":
                self.video_mgr.close_window(member_id)

    def update_stats(self, member_id, ping):
        if self.member_view:
            self.member_view.update_stats(member_id, ping)


    def append_chat(self, *args, **kwargs):
        if self.chat_view:
            self.chat_view.append_chat(*args, **kwargs)

    def add_file_transfer(self, *args, **kwargs):
        if self.chat_view:
            self.chat_view.add_file_transfer(*args, **kwargs)

    def update_file_progress(self, *args, **kwargs):
        if self.chat_view:
            self.chat_view.update_file_progress(*args, **kwargs)

    def complete_file_transfer(self, *args, **kwargs):
        if self.chat_view:
            self.chat_view.complete_file_transfer(*args, **kwargs)

    def show_vote_modal(self, target, vote_id):
        modal = ctk.CTkToplevel(self.root)
        modal.title("BANISH PROPOSAL")
        modal.geometry("400x200")
        modal.transient(self.root)
        modal.attributes("-topmost", True)
        modal.configure(fg_color=DANGER)
        
        def flash():
            if modal.winfo_exists():
                current = modal.cget("fg_color")
                modal.configure(fg_color=BG_COLOR if current == DANGER else DANGER)
                self.root.after(500, flash)
        flash()
        
        main_frame = ctk.CTkFrame(modal, fg_color=BG_COLOR, corner_radius=0, border_width=2, border_color=DANGER)
        main_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        csign = self.engine.callsign_map.get(target, target[:8])
        ctk.CTkLabel(main_frame, text=f"[ BANISH_PROPOSAL: {csign} ]", font=FONT_TITLE, text_color=DANGER).pack(pady=(20, 10))
        
        time_left = ctk.IntVar(value=60)
        lbl_timer = ctk.CTkLabel(main_frame, textvariable=time_left, font=FONT_BOLD, text_color=PRIMARY)
        lbl_timer.pack()
        
        btn_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        btn_frame.pack(pady=20)
        
        def cast(choice):
            self.engine.gov_mgr.cast_vote(target, vote_id, choice)
            modal.destroy()
            
        ctk.CTkButton(btn_frame, text="YES", fg_color="transparent", border_width=1, border_color=SUCCESS, text_color=SUCCESS, hover_color="#004433", width=80, corner_radius=0, command=lambda: cast("yes")).pack(side="left", padx=10)
        ctk.CTkButton(btn_frame, text="NO", fg_color="transparent", border_width=1, border_color=DANGER, text_color=DANGER, hover_color="#550011", width=80, corner_radius=0, command=lambda: cast("no")).pack(side="left", padx=10)
        
        def tick():
            if not modal.winfo_exists(): return
            t = time_left.get() - 1
            if t <= 0:
                modal.destroy()
            else:
                time_left.set(t)
                self.root.after(1000, tick)
        tick()

    def show_election_modal(self, round_num, candidates):
        modal = ctk.CTkToplevel(self.root)
        modal.title("ARCHON ELECTION")
        modal.geometry("400x400")
        modal.transient(self.root)
        modal.attributes("-topmost", True)
        modal.configure(fg_color=BG_COLOR)
        
        main_frame = ctk.CTkFrame(modal, fg_color=FRAME_COLOR, corner_radius=0, border_width=2, border_color=PRIMARY)
        main_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        ctk.CTkLabel(main_frame, text=f"[ ELECTION ROUND {round_num} ]", font=FONT_TITLE, text_color=PRIMARY).pack(pady=(20, 10))
        
        scroll = ctk.CTkScrollableFrame(main_frame, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=20, pady=10)
        
        def vote_for(cand):
            self.engine.gov_mgr.cast_election_vote(cand)
            modal.destroy()
            
        for cand in candidates:
            csign = self.engine.callsign_map.get(cand, cand[:8])
            ctk.CTkButton(scroll, text=csign, font=FONT_BOLD, fg_color="transparent", border_width=1, border_color=SECONDARY, text_color=SECONDARY, hover_color=SECONDARY_HOV, command=lambda c=cand: vote_for(c)).pack(pady=5, fill="x")
