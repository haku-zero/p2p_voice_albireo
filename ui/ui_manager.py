import customtkinter as ctk
from utils.i18n import get_text as _T
from utils import config
from utils.events import event_bus
from ui.theme import *
from ui.chat_view import ChatWindow
from ui.member_view import MemberView
from ui.modals import HostWizard, ClientWizard, VoteModal, ElectionModal
from ui.toast import ToastManager
from ui.video_view import VideoViewManager
from ui.top_bar import TopBarView
from ui.store import store

class UIManager:
    """
    UI 总体管理器 (UI Coordinator / Facade)。
    遵循单一职责 (SRP) 与高内聚低耦合原则：
    1. 负责协调全局窗口组件（TopBarView, MemberView, ChatWindow, VideoViewManager, ToastManager）；
    2. 注册系统事件总线 (EventBus) 与状态仓储 (AppStore) 数据驱动绑定；
    3. 弹窗协调委托给 ui.modals (HostWizard, ClientWizard, VoteModal, ElectionModal)。
    """
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
        self.top_bar = None
        self.toast_mgr = ToastManager(self.root)
        self.video_mgr = VideoViewManager(self.root, self.engine)
        self.share_btn = None
        self.current_role = None

        self._init_event_bindings()
        
        # 订阅全局状态仓储变更
        store.subscribe(self._on_store_changed)

    def _init_event_bindings(self):
        """绑定全局事件总线与 Store 分发"""
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
        event_bus.on("peer_ghost_state", lambda mid, ghost: self.root.after(0, lambda: store.dispatch("MEMBER_GHOST", {"peer_id": mid, "is_ghost": ghost})))
        event_bus.on("video_frame", lambda pid, arr: self.root.after(0, self.video_mgr.update_frame, pid, arr))

    def _on_store_changed(self, state):
        """响应 Store 状态驱动 MemberView 与 VideoViewManager"""
        if self.member_view:
            for pid, member in state["members"].items():
                status = member["status"]
                self.member_view.update_status(pid, status, self.toast_mgr.show_toast)
                self.member_view.update_talking_state(pid, member["talking_rms"])
                self.member_view.update_stats(pid, member["ping"])
                if status == "disconnected":
                    self.video_mgr.close_window(pid)

    def _on_chat_hidden(self):
        pass

    # --- 兼容性属性代理 (向下兼容直接访问控件引用的历史调用) ---
    @property
    def mic_btn(self):
        return getattr(self.top_bar, "mic_btn", None)

    @property
    def speaker_btn(self):
        return getattr(self.top_bar, "speaker_btn", None)

    @property
    def ptt_btn(self):
        return getattr(self.top_bar, "ptt_btn", None)

    def build_top_bar(self):
        """构建/重构顶部控制栏，委托给 TopBarView 独立组件"""
        if self.top_bar:
            self.top_bar.destroy()
            
        self.top_bar = TopBarView(
            parent=self.root,
            media_ctrl=self.media_ctrl,
            core_api=self.core_api,
            gov_api=self.gov_api,
            chat_view=self.chat_view,
            on_exit=self.exit_room
        )

    def change_mic_mode(self, mode):
        """委托给 TopBarView 处理"""
        if self.top_bar:
            return self.top_bar.change_mic_mode(mode)
        return self.media_ctrl.change_mic_mode(mode)

    def show_toast(self, message, timeout_ms=5000):
        """委托给 ToastManager"""
        self.toast_mgr.show_toast(message)

    def build_node_ui(self, work_frame):
        """构建主操作区域与成员拓扑列表"""
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
        ctk.CTkButton(top, text=_T("init_seq"), font=FONT_BOLD, corner_radius=0, fg_color="transparent", border_width=1, border_color=SUCCESS, text_color=SUCCESS, hover_color=SUCCESS_HOV, command=client_wizard.open).pack(side="left")
                      
        self.share_btn = ctk.CTkButton(top, text="[ SHARE_SCREEN ]", font=FONT_BOLD, corner_radius=0, fg_color="transparent", border_width=1, border_color=SECONDARY, text_color=SECONDARY, hover_color=SECONDARY_HOV, command=self.toggle_share)
        self.share_btn.pack(side="left", padx=10)
        
        members_frame = ctk.CTkScrollableFrame(main_area, label_text=_T("topology"), label_font=FONT_TITLE, fg_color=FRAME_COLOR, label_fg_color=BG_COLOR, label_text_color=PRIMARY, border_width=1, border_color=BORDER_COLOR)
        members_frame.pack(fill="both", expand=True, padx=20, pady=10)
        
        self.member_view = MemberView(members_frame, gov_api=self.gov_api, local_id=self.core_api.get_local_id())
        self.member_view.add_member(self.root.local_id, f"[ LOCAL_NODE ] {self.engine.callsign}")
        
        # Load persisted chat history
        self.root.after(100, self.chat_mgr.load_history)

    def toggle_share(self):
        """处理屏幕共享切换与权限校验"""
        if self.core_api.get_local_id() in getattr(self.gov_api, "share_banned_list", []):
            self.toast_mgr.show_toast("Permission Denied: Screen Share revoked by Archon.")
            return
            
        is_sharing = self.local_video.toggle_sharing()
        if is_sharing:
            self.share_btn.configure(text="[ STOP_SHARE ]", border_color=DANGER, text_color=DANGER, hover_color=DANGER_HOV)
        else:
            self.share_btn.configure(text="[ SHARE_SCREEN ]", border_color=SECONDARY, text_color=SECONDARY, hover_color=SECONDARY_HOV)

    def exit_room(self):
        """退出当前房间，重置各模块状态"""
        self.engine.reset()
        if self.chat_view:
            self.chat_view.destroy()
        if self.member_view:
            self.member_view.clear()
        if self.top_bar:
            self.top_bar.destroy()
            self.top_bar = None
        self.root.show_id_selection()

    def reset_room(self):
        if not self.member_view:
            return

    # --- Store 数据驱动辅助方法 ---
    def update_talking_state(self, member_id, rms):
        store.dispatch("UPDATE_MEMBER_STATS", {"peer_id": member_id, "rms": rms})

    def update_status(self, member_id, status):
        store.dispatch("MEMBER_JOINED" if status == "connected" else "MEMBER_LEFT", {"peer_id": member_id})

    def update_stats(self, member_id, ping):
        store.dispatch("UPDATE_MEMBER_STATS", {"peer_id": member_id, "ping": ping})

    # --- 聊天与文件传输委托 ---
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

    # --- 治理弹窗委托 ---
    def show_vote_modal(self, target, vote_id):
        VoteModal(self.root, self.gov_api, self.engine.callsign_map).open(target, vote_id)

    def show_election_modal(self, round_num, candidates):
        ElectionModal(self.root, self.gov_api, self.engine.callsign_map).open(round_num, candidates)
