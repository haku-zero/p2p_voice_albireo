import unittest
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import time
import asyncio
from unittest.mock import MagicMock

from infrastructure.signaling.signaling import SignalingCodec, SignalingPayload
from services.screen_share.sfu import SFUVideoManager
from services.voice.io import MicrophoneTrack
from ui.store import AppStore
from core.signaling_wizard import SignalingWizard

class DummyPlaybackManager:
    def __init__(self):
        pass
    def play_chunk(self, data):
        pass

class TestIssueFixes(unittest.TestCase):
    def test_issue1_sfu_active_video_detection(self):
        loop = asyncio.new_event_loop()
        sfu = SFUVideoManager(loop)
        
        # Initially no video
        self.assertFalse(sfu.has_active_video())
        
        # Feed 2x2 black placeholder (non-sharing state)
        sfu.latest_frames["peer_1"] = np.zeros((2, 2, 3), dtype=np.uint8)
        self.assertFalse(sfu.has_active_video())
        
        # Feed real active video frame
        sfu.latest_frames["peer_1"] = np.zeros((480, 640, 3), dtype=np.uint8)
        self.assertTrue(sfu.has_active_video())
        
        # Remove active frame
        sfu.latest_frames.pop("peer_1")
        self.assertFalse(sfu.has_active_video())
        loop.close()

    def test_issue2_signaling_callsign_decoding_and_wizard(self):
        sdp = "v=0\r\no=- 0 0 IN IP4 127.0.0.1\r\ns=-\r\n"
        sdp_type = "offer"
        remote_id = "8a775a05bba4cb35c500a72b8a79e934"
        callsign = "GhostRider"
        
        encoded = SignalingCodec.encode_offer(sdp, sdp_type, remote_id, callsign)
        
        # 1. Backwards compatibility: unpacks as 3-tuple
        dec_sdp, dec_type, dec_user = SignalingCodec.decode_payload(encoded)
        self.assertEqual(dec_sdp, sdp)
        self.assertEqual(dec_type, sdp_type)
        self.assertEqual(dec_user, remote_id)
        
        # 2. Contains callsign attribute
        decoded = SignalingCodec.decode_payload(encoded)
        self.assertIsInstance(decoded, SignalingPayload)
        self.assertEqual(decoded.callsign, callsign)
        
        # 3. Wizard records callsign into callsign_map
        engine = MagicMock()
        engine.callsign_map = {}
        engine.connections = {}
        engine.local_id = "host123"
        engine.callsign = "Commander"
        engine.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(engine.loop)
        engine.crypto = None
        wizard = SignalingWizard(engine)
        
        done_called = False
        def on_done(ans_str, r_id, err):
            nonlocal done_called
            done_called = True
            
        engine.loop.run_until_complete(wizard.host_accept_offer(encoded, on_done))
        self.assertTrue(done_called)
        self.assertEqual(engine.callsign_map.get(remote_id), callsign)
        engine.loop.close()

    def tearDown(self):
        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)

    def test_issue3_and_4_mic_level_and_frame_callbacks(self):
        playback = DummyPlaybackManager()
        track = MicrophoneTrack(playback)
        
        received_rms = []
        received_frames = []
        track.on_level_callback = lambda rms: received_rms.append(rms)
        track.on_frame_callback = lambda f: received_frames.append(f)
        
        # Feed synthetic audio into _audio_queue
        # 960 samples of 1000 Hz sine wave (amplitude 2000, RMS ~1414)
        samples = (np.sin(np.linspace(0, 10, 960)) * 2000).astype(np.int16).tobytes()
        track._audio_queue.put(samples)
        
        # Wait a short moment for pump thread to consume
        time.sleep(0.15)
        
        self.assertTrue(len(received_rms) > 0, "on_level_callback should have been called by pump worker")
        self.assertGreater(received_rms[0], 100.0, "RMS should reflect raw acoustic level")
        self.assertTrue(len(received_frames) > 0, "on_frame_callback should have received processed audio")
        self.assertEqual(len(received_frames[0]), len(samples))
        track.close()

    def test_issue2_store_callsign_updating(self):
        store = AppStore()
        
        # Node joins with initial ID prefix
        store.dispatch("MEMBER_JOINED", {"peer_id": "8a775a05", "callsign": "8a775a05"})
        self.assertEqual(store.get_state()["members"]["8a775a05"]["callsign"], "8a775a05")
        
        # Later update callsign
        store.dispatch("UPDATE_CALLSIGN", {"peer_id": "8a775a05", "callsign": "AlphaOne"})
        self.assertEqual(store.get_state()["members"]["8a775a05"]["callsign"], "AlphaOne")
        
        # Or MEMBER_JOINED refresh
        store.dispatch("MEMBER_JOINED", {"peer_id": "8a775a05", "callsign": "BravoTwo"})
        self.assertEqual(store.get_state()["members"]["8a775a05"]["callsign"], "BravoTwo")

    def test_issue_mic_mute_silence_and_zero_rms(self):
        playback = DummyPlaybackManager()
        track = MicrophoneTrack(playback)
        
        received_rms = []
        received_frames = []
        track.on_level_callback = lambda rms: received_rms.append(rms)
        track.on_frame_callback = lambda f: received_frames.append(f)
        
        # 1. When muted, pump worker MUST report 0.0 RMS and zeroed audio frames
        track.muted = True
        samples = (np.sin(np.linspace(0, 10, 960)) * 2000).astype(np.int16).tobytes()
        track._audio_queue.put(samples)
        
        time.sleep(0.15)
        
        self.assertTrue(len(received_rms) > 0, "Pump worker should have processed frame")
        self.assertEqual(received_rms[-1], 0.0, "RMS must be 0.0 when microphone is muted")
        self.assertTrue(len(received_frames) > 0, "on_frame_callback should have been called")
        self.assertEqual(received_frames[-1], b'\x00' * (track.samples_per_frame * 2), "Muted frame must be all zeros")
        
        # 2. recv() must also return silence when muted
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        frame = loop.run_until_complete(track.recv())
        frame_bytes = bytes(frame.planes[0])
        self.assertEqual(frame_bytes, b'\x00' * (track.samples_per_frame * 2), "recv() must return silent AudioFrame when muted")
        
        # 3. clear_buffers flushes queues
        track._audio_queue.put(b"test1")
        track._webrtc_queue.put(b"test2")
        track.clear_buffers()
        self.assertTrue(track._audio_queue.empty())
        self.assertTrue(track._webrtc_queue.empty())
        
        track.close()
        loop.close()

    def test_issue_peer_disconnect_and_router_events(self):
        from utils.events import event_bus
        from core.engine import WebRTCEngine
        from core.router import MessageRouter
        import json
        
        loop = asyncio.new_event_loop()
        engine = WebRTCEngine(loop)
        engine.is_host = True
        engine.local_id = "host_root"
        
        mock_channel = MagicMock()
        mock_channel.readyState = "open"
        engine.data_channels["client_1"] = {"control": mock_channel}
        engine.connections["client_1"] = MagicMock()
        
        status_events = []
        event_bus.on("status", lambda pid, st: status_events.append((pid, st)))
        
        # Trigger handle_peer_disconnected
        engine.handle_peer_disconnected("client_1")
        
        # Verify connection and channels cleared
        self.assertNotIn("client_1", engine.connections)
        self.assertNotIn("client_1", engine.data_channels)
        
        # Verify status event emitted
        self.assertIn(("client_1", "disconnected"), status_events)
        
        # Verify router handles incoming peer_left control message
        mock_api = MagicMock()
        mock_api.local_id = "local_peer"
        mock_api.callsign_map = {}
        mock_api.crypto.verify_payload.return_value = True
        mock_api.message_handlers = []
        mock_api._engine = engine
        
        router = MessageRouter(mock_api)
        peer_left_msg = json.dumps({"type": "peer_left", "peer_id": "client_2"})
        router.handle_message("relay_peer", "control", peer_left_msg)
        
        self.assertIn(("client_2", "disconnected"), status_events)
        loop.close()

    def test_store_room_reset_and_member_left(self):
        store = AppStore()
        store.dispatch("MEMBER_JOINED", {"peer_id": "node_x", "callsign": "NodeX"})
        self.assertEqual(store.get_state()["members"]["node_x"]["status"], "connected")
        
        store.dispatch("MEMBER_LEFT", {"peer_id": "node_x"})
        self.assertEqual(store.get_state()["members"]["node_x"]["status"], "disconnected")
        
        store.dispatch("RESET_ROOM")
        self.assertEqual(len(store.get_state()["members"]), 0)

if __name__ == "__main__":
    unittest.main()
