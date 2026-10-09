import asyncio
from core.api import CoreAPI
from governance.api import GovernanceAPI
from services.chat.manager import ChatManager
from services.file_transfer.manager import FileTransferManager
from services.voice.mixer import GlobalAudioMixer
from services.screen_share.sfu import SFUVideoManager
from infrastructure.signaling.mqtt_signaling import MQTTRelay
from utils.events import event_bus

class DummyPlaybackManager:
    def write_stereo(self, pcm): pass
    def shutdown(self): pass

class DaemonRunner:
    """
    Headless WebRTC Host SFU.
    Runs completely detached from UI and PyAudio, allowing deployment on Linux cloud servers.
    """
    def __init__(self, room_code):
        self.room_code = room_code
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        
        from infrastructure.db import LocalDB
        from infrastructure.crypto import CryptoManager
        self.db = LocalDB()
        self.crypto = CryptoManager()
        self.core_api = CoreAPI(self.loop, self.db, self.crypto)
        self.engine = self.core_api._engine
        self.gov_api = GovernanceAPI(self.core_api)
        self.chat_mgr = ChatManager(self.core_api, self.db)
        self.file_mgr = FileTransferManager(self.core_api, self.crypto)
        
        self.playback_mgr = DummyPlaybackManager()
        self.global_mixer = GlobalAudioMixer(self.playback_mgr)
        self.engine.mixer_ref = self.global_mixer
        self.sfu_video_mgr = SFUVideoManager(self.loop)
        
        self.global_mixer.start(self.loop)
        
        # Configure as Host
        self.core_api._engine.is_host = True
        
        from services.voice.mixer import NMinusOneMixerTrack
        self.core_api._engine.local_track_factories.append(
            lambda peer_id: NMinusOneMixerTrack(peer_id, self.global_mixer)
        )
        self.core_api._engine.local_track_factories.append(
            lambda peer_id: self.sfu_video_mgr.create_client_track()
        )
        
        from services.media_router import MediaRouter
        self.media_router = MediaRouter(self.core_api, self.playback_mgr, self.global_mixer, self.sfu_video_mgr, self.loop)
        self.core_api.register_track_handler(self.media_router.handle_daemon_track)
        
        def _on_peer_disconnected(peer_id):
            self.global_mixer.remove_track(peer_id)
            self.sfu_video_mgr.remove_track(peer_id)
            print(f"[Daemon] Peer left: {peer_id}")
            
        self.core_api.register_disconnect_handler(_on_peer_disconnected)
        event_bus.on("peer_left", _on_peer_disconnected)

    def start(self):
        self.core_api.set_callsign("Cloud_Archon")
        self.core_api.local_id = "host"
        self.core_api.reset_node()
        
        self.engine.is_host = True
        self.engine.room_code = self.room_code
        self.gov_api.state.is_archon = True
        self.gov_api.state.archon_id = self.core_api.local_id
        
        relay = MQTTRelay(self.room_code, self.engine)
        self.loop.create_task(relay.connect())
        
        print("="*50)
        print(f"🚀 Albireo Headless SFU Daemon")
        print(f"🔑 Room Code: {self.room_code}")
        print(f"🛡️  End-to-End Encryption enabled.")
        print(f"🎬 Video MCU Grid Compositor ready.")
        print(f"🎧 Audio MCU N-1 Matrix ready.")
        print("="*50)
        
        try:
            self.loop.run_forever()
        except KeyboardInterrupt:
            print("\n[Daemon] Shutting down...")
            self.loop.run_until_complete(self.engine.close())
            self.global_mixer.stop()
            self.loop.close()
