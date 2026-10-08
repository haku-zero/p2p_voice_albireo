import time
import customtkinter as ctk
from PIL import Image

class VideoViewManager:
    def __init__(self, root, engine):
        self.root = root
        self.engine = engine
        self.video_windows = {}

    def update_frame(self, peer_id, arr):
        if peer_id not in self.video_windows:
            vw = ctk.CTkToplevel(self.root)
            csign = self.engine.callsign_map.get(peer_id, peer_id[:8])
            vw.title(f"FEED: {csign}")
            vw.geometry("800x450")
            vw.configure(fg_color="#000000")
            vw.attributes("-topmost", True)
            
            lbl = ctk.CTkLabel(vw, text="")
            lbl.pack(fill="both", expand=True)
            
            def on_close():
                vw.destroy()
                if peer_id in self.video_windows:
                    del self.video_windows[peer_id]
            vw.protocol("WM_DELETE_WINDOW", on_close)
            
            self.video_windows[peer_id] = {"window": vw, "label": lbl, "last_update": 0}
            
        vw_state = self.video_windows[peer_id]
        if not vw_state["window"].winfo_exists(): return
        
        now = time.time()
        if now - vw_state["last_update"] < 1/15.0:
            return
        vw_state["last_update"] = now
        
        img = Image.fromarray(arr)
        
        w = vw_state["window"].winfo_width()
        h = vw_state["window"].winfo_height()
        if w < 10 or h < 10: 
            w, h = 800, 450
            
        ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(w, h))
        vw_state["label"].configure(image=ctk_img)
        vw_state["label"].image = ctk_img

    def close_window(self, peer_id):
        if peer_id in self.video_windows:
            if self.video_windows[peer_id]["window"].winfo_exists():
                self.video_windows[peer_id]["window"].destroy()
            del self.video_windows[peer_id]
