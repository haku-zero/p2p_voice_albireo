import os
import customtkinter as ctk
from PIL import Image
from utils.i18n import get_text as _T
from ui.theme import *

class ChatWindow:
    def __init__(self, root, engine, hide_callback):
        self.root = root
        self.engine = engine
        self.hide_callback = hide_callback
        
        self.window = None
        self.chat_scroll = None
        self.chat_entry = None
        self.chat_btn = None # Will be set by manager
        
        self.chat_progress_bars = {}

    def open(self):
        if self.chat_btn:
            self.chat_btn.configure(text=_T("chat"), border_color=PRIMARY, text_color=PRIMARY)
            
        if self.window is None or not self.window.winfo_exists():
            self.window = ctk.CTkToplevel(self.root)
            self.window.title("SECURE_CHANNEL")
            self.window.geometry("450x550")
            self.window.transient(self.root)
            self.window.configure(fg_color=BG_COLOR)
            
            self.chat_scroll = ctk.CTkScrollableFrame(self.window, fg_color=FRAME_COLOR, border_color=BORDER_COLOR, border_width=1)
            self.chat_scroll.pack(fill="both", expand=True, padx=10, pady=10)
            
            input_frame = ctk.CTkFrame(self.window, fg_color="transparent")
            input_frame.pack(fill="x", padx=10, pady=(0, 10))
            
            self.chat_entry = ctk.CTkEntry(input_frame, placeholder_text=">", font=FONT_MAIN, fg_color=BG_COLOR, border_color=PRIMARY, text_color=PRIMARY)
            self.chat_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
            self.chat_entry.bind("<Return>", lambda e: self.send_chat_msg())
            
            ctk.CTkButton(input_frame, text="[ TX ]", font=FONT_BOLD, width=50, fg_color="transparent", border_width=1, border_color=SUCCESS, text_color=SUCCESS, hover_color="#004433", command=self.send_chat_msg).pack(side="right")
            ctk.CTkButton(input_frame, text="[ + ]", font=FONT_BOLD, width=40, fg_color="transparent", border_width=1, border_color="#F59E0B", text_color="#F59E0B", hover_color="#B45309", command=self.send_file_dialog).pack(side="right", padx=(0, 5))
            
            self.window.protocol("WM_DELETE_WINDOW", self.hide)
        else:
            self.window.deiconify()
            self.window.focus()

    def hide(self):
        if self.window and self.window.winfo_exists():
            self.window.withdraw()
            if self.hide_callback:
                self.hide_callback()

    def destroy(self):
        if self.window and self.window.winfo_exists():
            self.window.destroy()
            self.window = None

    def send_chat_msg(self):
        msg = self.chat_entry.get().strip()
        if not msg: return
        self.chat_entry.delete(0, "end")
        self.append_chat(msg, sender=self.root.local_id)
        self.engine.send_chat(msg, self.root.local_id)

    def send_file_dialog(self):
        from tkinter import filedialog
        filepath = filedialog.askopenfilename()
        if filepath:
            file_id = self.engine.send_file(filepath, self.root.local_id)
            self.add_file_transfer(self.root.local_id, os.path.basename(filepath), os.path.getsize(filepath), file_id)

    def append_chat(self, text, is_system=False, image_path=None, sender="System"):
        if self.window is None or not self.window.winfo_exists():
            self.open()
            self.window.withdraw()
            
        msg_frame = ctk.CTkFrame(self.chat_scroll, fg_color=BG_COLOR if is_system else "#1A233A", corner_radius=8)
        msg_frame.pack(fill="x", padx=5, pady=5)
        
        lbl_sender = ctk.CTkLabel(msg_frame, text=sender, font=("Consolas", 10, "bold"), text_color=SECONDARY if is_system else PRIMARY)
        lbl_sender.pack(anchor="w", padx=10, pady=(5, 0))
        
        if text:
            lbl_text = ctk.CTkLabel(msg_frame, text=text, font=FONT_MAIN, text_color=TEXT_COLOR, justify="left", wraplength=380)
            lbl_text.pack(anchor="w", padx=10, pady=(0, 5))
            
        if image_path and os.path.exists(image_path):
            try:
                img = Image.open(image_path)
                img.thumbnail((300, 300))
                ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
                img_lbl = ctk.CTkLabel(msg_frame, text="", image=ctk_img)
                img_lbl.image = ctk_img  # Keep reference
                img_lbl.pack(anchor="w", padx=10, pady=(0, 10))
            except Exception as e:
                print(f"Failed to load image: {e}")
                
        self.root.after(50, lambda: self.chat_scroll._parent_canvas.yview_moveto(1.0))
        
        if not self.window.winfo_viewable() and not is_system and sender != self.root.local_id:
            if self.chat_btn:
                self.chat_btn.configure(text=_T("incoming_msg"), border_color=SUCCESS, text_color=SUCCESS)
        return msg_frame

    def add_file_transfer(self, sender, filename, size, file_id):
        text = f"{_T('uploading')} {filename} ({size} bytes)"
        msg_frame = self.append_chat(text, is_system=False, sender=sender)
        prog = ctk.CTkProgressBar(msg_frame, width=200, height=8, progress_color=SUCCESS)
        prog.set(0.0)
        prog.pack(anchor="w", padx=10, pady=(0, 10))
        self.chat_progress_bars[file_id] = {"prog": prog, "frame": msg_frame, "filename": filename}

    def update_file_progress(self, file_id, progress):
        if file_id in self.chat_progress_bars:
            self.chat_progress_bars[file_id]["prog"].set(progress)

    def complete_file_transfer(self, sender, filename, filepath, file_id):
        if file_id in self.chat_progress_bars:
            data = self.chat_progress_bars.pop(file_id)
            data["prog"].destroy()
            msg_frame = data["frame"]
            
            ext = os.path.splitext(filename)[1].lower()
            if ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'] and os.path.exists(filepath):
                try:
                    img = Image.open(filepath)
                    img.thumbnail((300, 300))
                    ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
                    img_lbl = ctk.CTkLabel(msg_frame, text="", image=ctk_img)
                    img_lbl.image = ctk_img
                    img_lbl.pack(anchor="w", padx=10, pady=(0, 10))
                except Exception:
                    pass
            else:
                lbl = ctk.CTkLabel(msg_frame, text="✅ Completed. Saved to downloads.", text_color=SUCCESS, font=("Consolas", 10))
                lbl.pack(anchor="w", padx=10, pady=(0, 10))
                
            self.root.after(50, lambda: self.chat_scroll._parent_canvas.yview_moveto(1.0))
        else:
            self.append_chat(f"✅ {filename} saved.", is_system=True, image_path=filepath if os.path.splitext(filename)[1].lower() in ['.jpg', '.png'] else None, sender=sender)
