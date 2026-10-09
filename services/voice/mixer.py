import threading
import numpy as np
from aiortc.contrib.media import MediaStreamTrack
from av import AudioFrame

class CustomMixerTrack(MediaStreamTrack):
    kind = "audio"
    def __init__(self, base_track):
        super().__init__()
        self.base_track = base_track
        self.lock = threading.Lock()
        self.source_buffers = {}
        
    def push_remote_audio(self, source_pc, data):
        with self.lock:
            if source_pc not in self.source_buffers:
                self.source_buffers[source_pc] = {"q": [], "buffering": True}
            
            state = self.source_buffers[source_pc]
            queue = state["q"]
            queue.append(data)
            
            # Stop buffering when we have enough frames to absorb jitter (60ms)
            if state["buffering"] and len(queue) >= 3:
                state["buffering"] = False
                
            # Aggressive jitter buffer drain to recover from delay accumulation
            if len(queue) > 8:
                while len(queue) > 3:
                    queue.pop(0)
                
    async def recv(self):
        frame = await self.base_track.recv()
        data = frame.to_ndarray().tobytes()
        
        arr1 = np.frombuffer(data, dtype=np.int16).astype(np.int32)
        
        with self.lock:
            for source_pc, state in list(self.source_buffers.items()):
                queue = state["q"]
                if not state["buffering"] and queue:
                    remote_data = queue.pop(0)
                    arr2 = np.frombuffer(remote_data, dtype=np.int16).astype(np.int32)
                    if len(arr1) == len(arr2):
                        # VAD: Only mix if RMS volume is above silence threshold
                        rms = np.sqrt(np.mean(np.square(arr2, dtype=np.float32)))
                        if rms > 30:
                            arr1 += arr2
                elif not queue:
                    # Underrun! Enter buffering mode to rebuild safety margin
                    state["buffering"] = True
                        
        mixed = np.clip(arr1, -32768, 32767).astype(np.int16)
        data = mixed.tobytes()
                
        new_frame = AudioFrame(format='s16', layout=frame.layout.name, samples=frame.samples)
        new_frame.planes[0].update(data)
        new_frame.sample_rate = frame.sample_rate
        new_frame.pts = frame.pts
        new_frame.time_base = frame.time_base
        return new_frame

import time
import fractions

class NMinusOneMixerTrack(MediaStreamTrack):
    kind = "audio"
    def __init__(self, target_peer_id, global_mixer):
        super().__init__()
        self.target_peer_id = target_peer_id
        self.global_mixer = global_mixer
        self.pts = 0
        self.sample_rate = 48000
        self.samples_per_frame = 960
        
    async def recv(self):
        import asyncio
        await asyncio.sleep(0.02)
        data = self.global_mixer.get_n_minus_one_audio(self.target_peer_id)
        frame = AudioFrame(format='s16', layout='mono', samples=self.samples_per_frame)
        frame.planes[0].update(data)
        frame.sample_rate = self.sample_rate
        frame.pts = self.pts
        self.pts += self.samples_per_frame
        frame.time_base = fractions.Fraction(1, self.sample_rate)
        return frame

class GlobalAudioMixer:
    def __init__(self, playback_mgr):
        self.playback_mgr = playback_mgr
        self.lock = threading.Lock()
        self.source_buffers = {}
        self._running = False
        self._thread = None
        self.n_minus_one_mixes = {} # {peer_id: bytes}
        self.local_mic_buffer = np.zeros(960, dtype=np.float32)
        
    def start(self, loop=None):
        self._running = True
        self._thread = threading.Thread(target=self._pump_loop, daemon=True)
        self._thread.start()
        
    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)
            
    def push_remote_audio(self, source_id, data):
        with self.lock:
            if source_id not in self.source_buffers:
                import hashlib
                import math
                h = int(hashlib.md5(source_id.encode()).hexdigest()[:8], 16)
                theta = (h / 0xFFFFFFFF) * 2 * math.pi
                pan = math.cos(theta)
                gL = math.sqrt(0.5 * (1 - pan))
                gR = math.sqrt(0.5 * (1 + pan))
                self.source_buffers[source_id] = {"q": [], "buffering": True, "gL": gL, "gR": gR}
            
            state = self.source_buffers[source_id]
            queue = state["q"]
            queue.append(data)
            
            if state["buffering"] and len(queue) >= 3:
                state["buffering"] = False
                
            if len(queue) > 8:
                while len(queue) > 3:
                    queue.pop(0)

    def set_local_mic(self, data):
        arr = np.frombuffer(data, dtype=np.int16).astype(np.float32)
        with self.lock:
            if len(arr) == 960:
                self.local_mic_buffer = arr
                    
    def remove_source(self, source_id):
        with self.lock:
            if source_id in self.source_buffers:
                del self.source_buffers[source_id]
                
    def get_n_minus_one_audio(self, peer_id):
        with self.lock:
            return self.n_minus_one_mixes.get(peer_id, b'\x00' * 1920)

    def _pump_loop(self):
        # Dedicated highly-precise OS thread, avoids asyncio GIL event loop stutter
        next_time = time.time()
        while self._running:
            left_arr = np.zeros(960, dtype=np.float32)
            right_arr = np.zeros(960, dtype=np.float32)
            has_audio = False
            
            active_sources = {}
            
            with self.lock:
                for source_id, state in list(self.source_buffers.items()):
                    queue = state["q"]
                    if not state["buffering"] and queue:
                        remote_data = queue.pop(0)
                        arr2 = np.frombuffer(remote_data, dtype=np.int16).astype(np.float32)
                        if len(left_arr) == len(arr2):
                            rms = np.sqrt(np.mean(np.square(arr2)))
                            if rms > 30:
                                left_arr += arr2 * state["gL"]
                                right_arr += arr2 * state["gR"]
                                active_sources[source_id] = arr2
                                has_audio = True
                    elif not queue:
                        state["buffering"] = True
                        
                # Create N-1 mixes for outbound relay
                local_arr = self.local_mic_buffer
                base_mono = np.zeros(960, dtype=np.float32)
                for sid, arr in active_sources.items():
                    base_mono += arr
                base_mono += local_arr # Include our own mic
                
                # Pre-calculate what each peer should hear (Everyone - Themselves)
                for target_id in self.source_buffers.keys():
                    n1_mix = base_mono.copy()
                    if target_id in active_sources:
                        n1_mix -= active_sources[target_id]
                    self.n_minus_one_mixes[target_id] = np.clip(n1_mix, -32768, 32767).astype(np.int16).tobytes()
                    
                # Store local mic in the N-1 mix for any peer not currently sending audio
                # This ensures they still hear us and other active speakers
                fallback_mix = np.clip(base_mono, -32768, 32767).astype(np.int16).tobytes()
                for target_id in list(self.source_buffers.keys()):
                    if target_id not in active_sources:
                        self.n_minus_one_mixes[target_id] = fallback_mix
                        
            if has_audio:
                stereo = np.empty(960 * 2, dtype=np.int16)
                stereo[0::2] = np.clip(left_arr, -32768, 32767).astype(np.int16)
                stereo[1::2] = np.clip(right_arr, -32768, 32767).astype(np.int16)
                self.playback_mgr.play_stereo_frame(stereo.tobytes())
                
            next_time += 0.02
            sleep_time = next_time - time.time()
            if sleep_time > 0:
                time.sleep(sleep_time)
            else:
                next_time = time.time()
