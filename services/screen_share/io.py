import asyncio
import time
import numpy as np
from PIL import Image
from aiortc import VideoStreamTrack
from av import VideoFrame

class DynamicVideoTrack(VideoStreamTrack):
    kind = "video"
    
    def __init__(self):
        super().__init__()
        self.sharing = False
        self.sct = None
        self.last_frame_time = 0
        self._black_img = np.zeros((2, 2, 3), dtype=np.uint8)
        
    def start_share(self):
        try:
            import mss
            self.sct = mss.mss()
            self.sharing = True
            print("[Video] Screen sharing started.")
        except ImportError:
            print("[Video] mss not installed. Cannot share screen.")
            
    def stop_share(self):
        self.sharing = False
        if self.sct:
            self.sct.close()
            self.sct = None
        print("[Video] Screen sharing stopped.")
        
    def toggle_sharing(self):
        if self.sharing:
            self.stop_share()
        else:
            self.start_share()
        return self.sharing

    async def recv(self):
        pts, time_base = await self.next_timestamp()
        
        if not self.sharing or not self.sct:
            await asyncio.sleep(1.0)
            frame = VideoFrame.from_ndarray(self._black_img, format="bgr24")
            frame.pts = pts
            frame.time_base = time_base
            return frame
            
        now = time.time()
        elapsed = now - self.last_frame_time
        if elapsed < 1.0 / 15.0:
            await asyncio.sleep((1.0/15.0) - elapsed)
            
        self.last_frame_time = time.time()
        
        try:
            monitor = self.sct.monitors[1]
            sct_img = self.sct.grab(monitor)
            img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
            img.thumbnail((1280, 720), Image.Resampling.LANCZOS)
            arr = np.array(img)
            frame = VideoFrame.from_ndarray(arr, format="rgb24")
            frame.pts = pts
            frame.time_base = time_base
            return frame
        except Exception as e:
            print(f"[Video] Capture error: {e}")
            await asyncio.sleep(1.0)
            frame = VideoFrame.from_ndarray(self._black_img, format="bgr24")
            frame.pts = pts
            frame.time_base = time_base
            return frame

def start_video_receive_loop(track, on_frame_callback):
    import asyncio
    async def _consume():
        try:
            while True:
                frame = await track.recv()
                arr = frame.to_ndarray(format="rgb24")
                if arr.shape[0] > 2:
                    on_frame_callback(arr)
        except Exception as e:
            pass
    asyncio.create_task(_consume())
