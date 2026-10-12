import unittest
import asyncio
import numpy as np
from services.voice.io import MicrophoneTrack
from ui.audio_visualizer import AudioVisualizer
from core.peer import PeerConnection
from core.engine import WebRTCEngine
from infrastructure.crypto import CryptoManager
from infrastructure.signaling.signaling import SignalingCodec

class DummyPlaybackManager:
    def __init__(self):
        pass
    def play_chunk(self, data):
        pass

class TestNextGenFeatures(unittest.TestCase):
    def test_smart_vad_hysteresis_and_hangover(self):
        playback = DummyPlaybackManager()
        track = MicrophoneTrack(playback)
        
        # Initially closed
        self.assertFalse(track._voice_active)
        self.assertEqual(track._hangover_counter, 0)
        
        # Test sub-threshold noise (RMS < 220) - gate remains closed
        noise_samples = (np.sin(np.linspace(0, 10, 960)) * 50).astype(np.int16).tobytes()
        frame1, rms1, active1 = track.process_audio_frame(noise_samples)
        self.assertFalse(track._voice_active)
        self.assertFalse(active1)
        # Should be muted (zeros)
        self.assertEqual(frame1, b'\x00' * len(noise_samples))
        
        # Test voice burst exceeding attack_threshold (> 450) - gate opens
        loud_samples = (np.sin(np.linspace(0, 10, 960)) * 2000).astype(np.int16).tobytes()
        frame2, rms2, active2 = track.process_audio_frame(loud_samples)
        self.assertTrue(track._voice_active)
        self.assertTrue(active2)
        self.assertEqual(track._hangover_counter, 15)
        # Should NOT be zeroed
        self.assertNotEqual(frame2, b'\x00' * len(loud_samples))
        
        # Test medium sound falling below attack (e.g., 300) but above release (220) - hysteresis keeps gate open
        mid_samples = (np.sin(np.linspace(0, 10, 960)) * 400).astype(np.int16).tobytes()
        frame3, rms3, active3 = track.process_audio_frame(mid_samples)
        self.assertTrue(track._voice_active)
        self.assertTrue(active3)
        
        # Test low-level tail sound (RMS ~70, below release 220) - hangover counter decrements for 15 frames before closing
        tail_samples = (np.sin(np.linspace(0, 10, 960)) * 100).astype(np.int16).tobytes()
        for i in range(14):
            f, r, act = track.process_audio_frame(tail_samples)
            self.assertTrue(track._voice_active, f"Gate should stay open during hangover frame {i}")
            self.assertTrue(act)
            self.assertEqual(f, tail_samples) # Natural tail audio preserved, not muted
            
        # 15th frame decrements counter to 0 -> closes gate on next frame
        f15, r15, act15 = track.process_audio_frame(tail_samples)
        self.assertFalse(track._voice_active)
        self.assertFalse(act15)
        self.assertEqual(f15, b'\x00' * len(tail_samples)) # Closed: muted to zeroes

    def test_peer_force_relay_filtering(self):
        loop = asyncio.new_event_loop()
        engine = WebRTCEngine(loop)
        peer = PeerConnection("test_relay_peer", loop, engine, force_relay=True)
        self.assertTrue(peer.force_relay)
        
        sample_sdp = (
            "v=0\r\n"
            "a=candidate:1 1 UDP 2130706431 192.168.1.100 50000 typ host\r\n"
            "a=candidate:2 1 UDP 1694498815 203.0.113.1 50001 typ srflx raddr 192.168.1.100 rport 50000\r\n"
            "a=candidate:3 1 UDP 84180991 198.51.100.2 50002 typ relay raddr 203.0.113.1 rport 50001\r\n"
        )
        filtered_sdp = peer._filter_relay_candidates(sample_sdp)
        self.assertIn("typ relay", filtered_sdp)
        self.assertNotIn("typ host", filtered_sdp)
        self.assertNotIn("typ srflx", filtered_sdp)
        loop.close()

    def test_ghost_grace_period_initialization(self):
        loop = asyncio.new_event_loop()
        engine = WebRTCEngine(loop)
        peer = PeerConnection("ghost_test_peer", loop, engine)
        self.assertFalse(peer._is_ghost)
        self.assertIsNone(peer._disconnect_timer)
        loop.close()

if __name__ == "__main__":
    unittest.main()
