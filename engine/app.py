import threading
import asyncio
from core.api import CoreAPI
from governance.api import GovernanceAPI
from services.voice.io import get_audio_devices, MicrophoneTrack, PlaybackManager
from services.voice.mixer import GlobalAudioMixer
from services.screen_share.io import DynamicVideoTrack
from services.chat.manager import ChatManager
from services.file_transfer.manager import FileTransferManager
from ui.ui_manager import UIManager
from ui.theme import *
from utils.events import event_bus
from ui.main_window import MainWindow

class AppRunner:
    """
    Application Bootstrapper / Composition Root.
    Assembles the dependencies and controls application lifecycle.
    """
    def __init__(self):
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self._run_async_loop, daemon=True).start()
        
        self.root = MainWindow(self.handle_login, self._real_quit)
        
        from infrastructure.db import LocalDB
        from infrastructure.crypto import CryptoManager
        self.db = LocalDB()
        self.crypto = CryptoManager()
        
        # 1. Core API (Gateway)
        self.core_api = CoreAPI(self.loop, self.db, self.crypto)
        self.engine = self.core_api._engine # Transitional monkey patch reference
        self.engine.core_api_ref = self.core_api
        
        # 3. Media Services
        self.inputs_map, self.outputs_map = get_audio_devices()
        self.playback_mgr = PlaybackManager()
        self.local_mic = MicrophoneTrack(self.playback_mgr)
        self.local_video = DynamicVideoTrack()
        self.global_mixer = GlobalAudioMixer(self.playback_mgr)
        self.engine.mixer_ref = self.global_mixer
        self.global_mixer.start(self.loop)
        
        from services.screen_share.sfu import SFUVideoManager
        self.sfu_video_mgr = SFUVideoManager(self.loop)
        
        async def _host_video_viewer():
            while True:
                await asyncio.sleep(1.0 / 15.0)
                if getattr(self.core_api._engine, "is_host", False):
                    grid = self.sfu_video_mgr.get_composited_canvas()
                    event_bus.emit("video_frame", "host_mcu", grid)
        self.loop.create_task(_host_video_viewer())
        
        def on_sfu_migration(new_host_id):
            if self.core_api.local_id == new_host_id:
                from services.voice.mixer import NMinusOneMixerTrack
                self.core_api._engine.local_track_factories = [
                    lambda peer_id: NMinusOneMixerTrack(peer_id, self.global_mixer),
                    lambda peer_id: self.sfu_video_mgr.create_client_track()
                ]
        event_bus.on("sfu_migration_triggered", on_sfu_migration)

        def on_local_mic_frame(data):
            self.global_mixer.set_local_mic(data)
        self.local_mic.on_frame_callback = on_local_mic_frame
        
        from services.media_router import MediaRouter
        self.media_router = MediaRouter(self.core_api, self.playback_mgr, self.global_mixer, self.sfu_video_mgr, self.loop)
        self.core_api.register_track_handler(self.media_router.handle_client_track)
        
        # 5. Business Services
        self.gov_api = GovernanceAPI(self.core_api)
        self.chat_mgr = ChatManager(self.core_api, self.db)
        self.file_mgr = FileTransferManager(self.core_api, self.crypto)
        
        # 6. UI
        from ui.media_controller import MediaController
        self.media_ctrl = MediaController(self.local_mic, self.playback_mgr, self.inputs_map, self.outputs_map)
        
        self.ui_ctrl = UIManager(
            self.root, self.engine, self.core_api, self.gov_api, self.chat_mgr, self.file_mgr,
            self.media_ctrl, self.loop, self.local_video
        )

    def start(self):
        self.root.show_id_selection()
        self.root.mainloop()

    def _run_async_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()
        event_bus.on("all_disconnected", lambda: self.root.after(0, self.handle_all_disconnected))
        event_bus.on("room_ended_by_archon", lambda: self.root.after(0, self.handle_room_ended))

    def handle_room_ended(self):
        event_bus.emit("toast", "Room forcibly disbanded by Archon.")
        self.db.clear_chat_history()
        self.core_api.reset_node()
        self.ui_ctrl.reset_room()
        self.root.show_id_selection()

    def handle_all_disconnected(self):
        self.db.clear_chat_history()
        self.core_api.reset_node()
        self.ui_ctrl.reset_room()

    def handle_login(self, uid):
        self.core_api.set_callsign(uid)
        self.root.local_id = self.core_api.get_local_id()
        self.enter_room('node')

    def enter_room(self, role):
        for widget in self.root.winfo_children():
            widget.destroy()
            
        if role == 'host':
            from services.voice.mixer import NMinusOneMixerTrack
            self.core_api._engine.is_host = True
            self.core_api._engine.local_track_factories.append(
                lambda peer_id: NMinusOneMixerTrack(peer_id, self.global_mixer)
            )
            self.core_api._engine.local_track_factories.append(
                lambda peer_id: self.sfu_video_mgr.create_client_track()
            )
        else:
            self.core_api._engine.local_tracks.append(self.local_mic)
            self.core_api._engine.local_tracks.append(self.local_video)
            
        self.root.configure(fg_color=BG_COLOR)
        self.ui_ctrl.build_top_bar()
        
        import customtkinter as ctk
        work_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        work_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        self.ui_ctrl.build_node_ui(work_frame)

    def _real_quit(self):
        self.db.clear_chat_history()
        self.core_api.reset_node()
        self.playback_mgr.shutdown()
        self.global_mixer.stop()
        if hasattr(self, 'loop') and self.loop.is_running():
            self.loop.call_soon_threadsafe(self.loop.stop)
        self.root.destroy()
