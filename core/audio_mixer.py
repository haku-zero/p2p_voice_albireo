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
                
            # Simple jitter buffer limit to prevent delay accumulation
            if len(queue) > 8:
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
                        arr1 += arr2
                elif not queue:
                    # Underrun! Enter buffering mode to rebuild safety margin
                    state["buffering"] = True
                        
        mixed = np.clip(arr1, -32768, 32767).astype(np.int16)
        data = mixed.tobytes()
                
        new_frame = AudioFrame(format='s16', layout='mono', samples=frame.samples)
        new_frame.planes[0].update(data)
        new_frame.sample_rate = frame.sample_rate
        new_frame.pts = frame.pts
        new_frame.time_base = frame.time_base
        return new_frame
