import customtkinter as ctk
from utils.i18n import get_text as _T
from utils import config
from ui.theme import *
from ui.chat_view import ChatWindow
from ui.member_view import MemberView
from ui.modals import HostWizard, ClientWizard
from ui.toast import ToastManager
from ui.video_view import VideoViewManager
from ui.store import store

class UIManager:
    def __init__(self, app_root, webrtc_engine, core_api, gov_api, chat_mgr, file_mgr, media_ctrl, loop, local_video):
        self.root = app_root
        self.engine = webrtc_engine
        self.core_api = core_api
        self.gov_api = gov_api
        self.chat_mgr = chat_mgr
        self.file_mgr = file_mgr
        self.media_ctrl = media_ctrl
        self.loop = loop
        self.local_video = local_video
        
        # Monkey patch legacy engine usage in UI modules for transitional compatibility
        self.engine.chat_mgr = self.chat_mgr
        self.engine.file_manager = self.file_mgr
        self.engine.gov_mgr = self.gov_api
        self.engine.local_video = self.local_video
        self.engine.callsign_map = self.core_api.callsign_map
        self.engine.local_id = self.core_api.get_local_id()
        
        self.chat_view = ChatWindow(self.root, self.engine, self._on_chat_hidden)
        self.member_view = None
        self.toast_mgr = ToastManager(self.root)
        self.video_mgr = VideoViewManager(self.root, self.engine)

        from utils.events import event_bus
        event_bus.on("toast", lambda msg: self.root.after(0, self.toast_mgr.show_toast, msg))
        event_bus.on("talking", lambda mid, rms: self.root.after(0, lambda: store.dispatch("UPDATE_MEMBER_STATS", {"peer_id": mid, "rms": rms})))
        event_bus.on("local_mic_level", lambda rms: self.root.after(0, lambda: store.dispatch("UPDATE_MEMBER_STATS", {"peer_id": self.root.local_id, "rms": rms})))
        event_bus.on("status", lambda mid, st: self.root.after(0, lambda: store.dispatch("MEMBER_JOINED" if st == "connected" else "MEMBER_LEFT", {"peer_id": mid})))
        event_bus.on("stats", lambda mid, ping: self.root.after(0, lambda: store.dispatch("UPDATE_MEMBER_STATS", {"peer_id": mid, "ping": ping})))
        event_bus.on("chat_message", lambda mid, msg: self.root.after(0, self.append_chat, msg, False, None, mid))
        event_bus.on("file_incoming", lambda mid, fn, sz, fid: self.root.after(0, self.add_file_transfer, mid, fn, sz, fid))
        event_bus.on("file_done", lambda mid, fn, fp, fid: self.root.after(0, self.complete_file_transfer, mid, fn, fp, fid))
        event_bus.on("file_progress", lambda mid, prog, fid: self.root.after(0, self.update_file_progress, fid, prog))
        event_bus.on("vote_requested", lambda target, vid: self.root.after(0, self.show_vote_modal, target, vid))
        event_bus.on("election_requested", lambda rnd, cand: self.root.after(0, self.show_election_modal, rnd, cand))
        event_bus.on("video_frame", lambda pid, arr: self.root.after(0, self.video_mgr.update_frame, pid, arr))
        
        # Subscribe UI to the Store (Data Binding)
        store.subscribe(self._on_store_changed)

    def _on_store_changed(self, state):
        # Data-Binding: Auto-sync UI widgets with State Dictionary
        
        # Update Mic Button UI
        if hasattr(self, 'mic_btn'):
            if state["mic_muted"]:
                self.mic_btn.configure(text=_T("mic_muted"), border_color=DANGER, text_color=DANGER)
            else:
                self.mic_btn.configure(text=_T("mic_on"), border_color=PRIMARY, text_color=PRIMARY)
                
        # Update Speaker Button UI
        if hasattr(self, 'speaker_btn'):
            if state["speaker_muted"]:
                self.speaker_btn.configure(text=_T("spk_muted"), border_color=DANGER, text_color=DANGER)
            else:
                self.speaker_btn.configure(text=_T("spk_on"), border_color=SECONDARY, text_color=SECONDARY)
                
        # Update Topology (MemberView) 
        if self.member_view:
            for pid, member in state["members"].items():
                status = member["status"]
                self.member_view.update_status(pid, status, self.toast_mgr.show_toast)
                self.member_view.update_talking_state(pid, member["talking_rms"])
                self.member_view.update_stats(pid, member["ping"])
                if status == "disconnected":
                    self.video_mgr.close_window(pid)

    def _on_chat_hidden(self):
        # Callback when chat is hidden/closed
        pass

    def build_top_bar(self):
        top_container = ctk.CTkFrame(self.root, fg_color="transparent")
        top_container.pack(fill="x", padx=10, pady=5)
        
        row0 = ctk.CTkFrame(top_container, fg_color="transparent")
        row0.pack(fill="x", pady=(0, 5))
        ctk.CTkButton(row0, text=_T("exit_link"), width=120, font=FONT_BOLD, corner_radius=0, fg_color="transparent", border_width=1, border_color=DANGER, text_color=DANGER, hover_color=DANGER_HOV, command=self.exit_room).pack(side="left")
        
        from ui.network_settings import NetworkSettingsModal
        net_btn = ctk.CTkButton(row0, text="[ NAT Settings ]", width=120, font=FONT_BOLD, corner_radius=0, fg_color="transparent", border_width=1, border_color=PRIMARY, text_color=PRIMARY, hover_color=PRIMARY_HOV, command=NetworkSettingsModal(self.root).open)
        net_btn.pack(side="right", padx=10)
        
        if getattr(self.core_api._engine, "is_host", False):
            ctk.CTkButton(row0, text="[ Disband Room ]", width=120, font=FONT_BOLD, corner_radius=0, fg_color="transparent", border_width=1, border_color=DANGER, text_color=DANGER, hover_color=DANGER_HOV, command=self.gov_api.issue_end_room).pack(side="left", padx=10)
        
        row1 = ctk.CTkFrame(top_container, fg_color="transparent")
        row1.pack(fill="x", pady=2)
        
        ctk.CTkLabel(row1, text=_T("audio_in"), font=FONT_MAIN, text_color=TEXT_COLOR).pack(side="left", padx=2)
        self.in_combo = ctk.CTkComboBox(row1, values=list(self.media_ctrl.inputs_map.keys()), command=self.media_ctrl.change_in_device, width=220, font=FONT_MAIN, fg_color=FRAME_COLOR, border_color=BORDER_COLOR, button_color=BORDER_COLOR, button_hover_color=PRIMARY, text_color=PRIMARY)
        self.in_combo.pack(side="left", padx=5)
        
        ctk.CTkLabel(row1, text=_T("audio_out"), font=FONT_MAIN, text_color=TEXT_COLOR).pack(side="left", padx=(15, 2))
        self.out_combo = ctk.CTkComboBox(row1, values=list(self.media_ctrl.outputs_map.keys()), command=self.media_ctrl.change_out_device, width=220, font=FONT_MAIN, fg_color=FRAME_COLOR, border_color=BORDER_COLOR, button_color=BORDER_COLOR, button_hover_color=PRIMARY, text_color=PRIMARY)
        self.out_combo.pack(side="left", padx=5)
        
        cfg = config.load_config()
        saved_in = cfg.get("in_device")
        in_names = list(self.media_ctrl.inputs_map.keys())
        if saved_in not in in_names and in_names:
            saved_in = in_names[0]
        if saved_in:
            self.in_combo.set(saved_in)
            self.media_ctrl.change_in_device(saved_in)
            
        saved_out = cfg.get("out_device")
        out_names = list(self.media_ctrl.outputs_map.keys())
        if saved_out not in out_names and out_names:
            saved_out = out_names[0]
        if saved_out:
            self.out_combo.set(saved_out)
            self.media_ctrl.change_out_device(saved_out)
            
        config.save_config("in_device", saved_in)
        config.save_config("out_device", saved_out)
        
        row2 = ctk.CTkFrame(top_container, fg_color="transparent")
        row2.pack(fill="x", pady=8)
        
        self.mic_btn = ctk.CTkButton(row2, text=_T("mic_on"), font=FONT_BOLD, width=100, corner_radius=0, fg_color="transparent", border_width=1, border_color=PRIMARY, text_color=PRIMARY, hover_color=PRIMARY_HOV, command=self.media_ctrl.toggle_mic)
        self.mic_btn.pack(side="left", padx=2)
        
        self.mic_vol_slider = ctk.CTkSlider(row2, from_=0, to=1.0, width=80, command=self.media_ctrl.change_mic_volume, button_color=PRIMARY, button_hover_color=SUCCESS, progress_color=PRIMARY)
        saved_mic_vol = config.load_config().get("mic_vol", 1.0)
        self.mic_vol_slider.set(saved_mic_vol)
        self.media_ctrl.change_mic_volume(saved_mic_vol)
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
        
        self.speaker_btn = ctk.CTkButton(row2, text=_T("spk_on"), font=FONT_BOLD, width=100, corner_radius=0, fg_color="transparent", border_width=1, border_color=SECONDARY, text_color=SECONDARY, hover_color=SECONDARY_HOV, command=self.media_ctrl.toggle_speaker)
        self.speaker_btn.pack(side="left", padx=(15, 2))
        
        self.vol_slider = ctk.CTkSlider(row2, from_=0, to=1.0, width=100, command=self.media_ctrl.change_speaker_volume, button_color=SECONDARY, button_hover_color=SUCCESS, progress_color=SECONDARY)
        saved_spk_vol = config.load_config().get("speaker_vol", 0.1)
        self.vol_slider.set(saved_spk_vol)
        self.media_ctrl.change_speaker_volume(saved_spk_vol)
        self.vol_slider.bind("<ButtonRelease-1>", lambda e: self.media_ctrl.playback_mgr.play_beep())
        self.vol_slider.pack(side="left", padx=5)
        
        self.chat_btn = ctk.CTkButton(row2, text=_T("chat"), font=FONT_BOLD, width=120, corner_radius=0, fg_color="transparent", border_width=1, border_color=PRIMARY, text_color=PRIMARY, hover_color=PRIMARY_HOV, command=self.chat_view.open)
        self.chat_btn.pack(side="right", padx=10)
        self.chat_view.chat_btn = self.chat_btn

    def change_mic_mode(self, mode):
        res = self.media_ctrl.change_mic_mode(mode)
        if res == "ptt":
            self.ptt_btn.configure(state="normal", text=_T("hold_tx"), border_color=PRIMARY, text_color=PRIMARY)
            self.mic_btn.configure(state="disabled", text=_T("mic_lock"), border_color=BORDER_COLOR, text_color=BORDER_COLOR)
        else:
            self.ptt_btn.configure(state="disabled", text=_T("ptt_stdby"), border_color=BORDER_COLOR, text_color=BORDER_COLOR)
            self.mic_btn.configure(state="normal", text=_T("mic_on"), border_color=PRIMARY, text_color=PRIMARY)

    def ptt_press(self, event):
        if self.ptt_btn.cget("state") == "normal":
            self.media_ctrl.handle_ptt(True)
            self.ptt_btn.configure(fg_color=SUCCESS, text_color=BG_COLOR, text=_T("tx_active"))

    def ptt_release(self, event):
        if self.ptt_btn.cget("state") == "normal":
            self.media_ctrl.handle_ptt(False)
            self.ptt_btn.configure(fg_color="transparent", text_color=PRIMARY, text=_T("hold_tx"))



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
                store.dispatch("MEMBER_JOINED", {"peer_id": remote_id, "callsign": csign})
                
            # Request chat history sync from the Host (Archon)
            if not getattr(self.engine, "is_host", False):
                self.chat_mgr.request_sync(remote_id)
                
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
        
        # Load persisted chat history
        self.root.after(100, self.chat_mgr.load_history)

    def toggle_share(self):
        if self.core_api.get_local_id() in getattr(self.gov_api, "share_banned_list", []):
            self.toast_mgr.show_toast("Permission Denied: Screen Share revoked by Archon.")
            return
            
        is_sharing = self.local_video.toggle_sharing()
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
        store.dispatch("UPDATE_MEMBER_STATS", {"peer_id": member_id, "rms": rms})

    def update_status(self, member_id, status):
        store.dispatch("MEMBER_JOINED" if status == "connected" else "MEMBER_LEFT", {"peer_id": member_id})

    def update_stats(self, member_id, ping):
        store.dispatch("UPDATE_MEMBER_STATS", {"peer_id": member_id, "ping": ping})


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
            self.gov_api.cast_vote(target, vote_id, choice)
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
            self.gov_api.cast_election_vote(cand)
            modal.destroy()
            
        for cand in candidates:
            csign = self.engine.callsign_map.get(cand, cand[:8])
            ctk.CTkButton(scroll, text=csign, font=FONT_BOLD, fg_color="transparent", border_width=1, border_color=SECONDARY, text_color=SECONDARY, hover_color=SECONDARY_HOV, command=lambda c=cand: vote_for(c)).pack(pady=5, fill="x")
