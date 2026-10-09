from utils.events import event_bus

class MediaRouter:
    """
    Routes WebRTC media tracks (Audio/Video) to the appropriate consumers (Mixer, SFU Video Manager, Playback).
    Decouples media processing logic from the application bootstrapper.
    """
    def __init__(self, core_api, playback_mgr, global_mixer, sfu_video_mgr, loop):
        self.core_api = core_api
        self.playback_mgr = playback_mgr
        self.global_mixer = global_mixer
        self.sfu_video_mgr = sfu_video_mgr
        self.loop = loop

    def handle_client_track(self, peer_id, track):
        if track.kind == "audio":
            def on_level(rms):
                event_bus.emit("talking", peer_id, rms)
                if rms > 0.05 and getattr(self.core_api._engine, "is_host", False):
                    self.sfu_video_mgr.set_active_speaker(peer_id)
            def on_frame(data):
                self.global_mixer.push_remote_audio(peer_id, data)
            from services.voice.io import start_playback_loop
            start_playback_loop(track, self.playback_mgr, on_level, on_frame, play_local=False)
        elif track.kind == "video":
            if getattr(self.core_api._engine, "is_host", False):
                self.sfu_video_mgr.add_track(peer_id, track)
            else:
                def on_video_frame(arr):
                    event_bus.emit("video_frame", peer_id, arr)
                from services.screen_share.io import start_video_receive_loop
                start_video_receive_loop(track, on_video_frame)

    def handle_daemon_track(self, peer_id, track):
        if track.kind == "audio":
            async def _consume_audio():
                try:
                    while True:
                        frame = await track.recv()
                        data = frame.to_ndarray().tobytes()
                        self.global_mixer.push_remote_audio(peer_id, data)
                except Exception as e:
                    print(f"[Daemon] Audio track error {peer_id}: {e}")
            self.loop.create_task(_consume_audio())
        elif track.kind == "video":
            self.sfu_video_mgr.add_track(peer_id, track)
