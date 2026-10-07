import threading
import asyncio
import customtkinter as ctk
import pystray
from PIL import Image, ImageDraw
from utils import config
from core.audio_io import get_audio_devices, MicrophoneTrack, PlaybackManager
from core.engine import WebRTCEngine
from ui import UIManager
from utils.i18n import get_text as _T

class AppRunner(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Albireo")
        self.geometry("850x680")
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.tray_icon = None
        
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self._run_async_loop, daemon=True).start()
        
        self.inputs_map, self.outputs_map = get_audio_devices()
        self.playback_mgr = PlaybackManager()
        self.local_mic = MicrophoneTrack(self.playback_mgr)
        
        self.engine = WebRTCEngine(self.local_mic, self.playback_mgr, self.loop, self.on_webrtc_event)
        
        self.ui_ctrl = UIManager(self, self.engine, self.inputs_map, self.outputs_map, 
                                    self.local_mic, self.playback_mgr, self.loop)
        
        self.local_id = "User"

    def start(self):
        self.show_id_selection()
        self.mainloop()

    def _run_async_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def on_webrtc_event(self, event_type, **kwargs):
        member_id = kwargs.get("member_id")
        if event_type == "talking":
            rms = kwargs.get("rms", 0)
            self.after(0, self.ui_ctrl.update_talking_state, member_id, rms)
        elif event_type == "status":
            status = kwargs.get("status")
            self.after(0, self.ui_ctrl.update_status, member_id, status)
        elif event_type == "stats":
            ping = kwargs.get("ping", 0)
            self.after(0, self.ui_ctrl.update_stats, member_id, ping)
        elif event_type == "chat_message":
            msg = kwargs.get("message", "")
            self.after(0, self.ui_ctrl.append_chat, msg, False, None, member_id)
        elif event_type == "local_mic_level":
            rms = kwargs.get("rms", 0.0)
            self.after(0, self.ui_ctrl.update_talking_state, self.local_id, rms)
        elif event_type == "file_incoming":
            fname = kwargs.get("filename", "")
            sz = kwargs.get("size", 0)
            file_id = kwargs.get("file_id")
            self.after(0, self.ui_ctrl.add_file_transfer, member_id, fname, sz, file_id)
        elif event_type == "file_done":
            fname = kwargs.get("filename", "")
            fpath = kwargs.get("filepath", "")
            file_id = kwargs.get("file_id")
            self.after(0, self.ui_ctrl.complete_file_transfer, member_id, fname, fpath, file_id)
        elif event_type == "file_progress":
            file_id = kwargs.get("file_id")
            progress = kwargs.get("progress", 0.0)
            self.after(0, self.ui_ctrl.update_file_progress, file_id, progress)
        elif event_type == "all_disconnected":
            self.after(0, self.handle_all_disconnected)

    def handle_all_disconnected(self):
        self.engine.reset()
        self.ui_ctrl.reset_room()

    def show_id_selection(self):
        for widget in self.winfo_children():
            widget.destroy()
        self.configure(fg_color="#090C15")
        frame = ctk.CTkFrame(self, fg_color="#111726", corner_radius=2, border_width=1, border_color="#1E293B")
        frame.pack(pady=100, padx=50, fill="both", expand=True)
        ctk.CTkLabel(frame, text=_T("sys_init"), font=("Consolas", 24, "bold"), text_color="#00F0FF").pack(pady=30)
        self.id_entry = ctk.CTkEntry(frame, placeholder_text=_T("input_callsign"), height=40, corner_radius=2, font=("Consolas", 14), border_color="#00F0FF", fg_color="#090C15", text_color="#00F0FF")
        
        saved_id = config.load_config().get("local_id", "")
        if saved_id:
            self.id_entry.insert(0, saved_id)
            
        self.id_entry.pack(pady=20, padx=50, fill="x")
        self.id_entry.bind("<Return>", lambda e: self.submit_id())
        ctk.CTkButton(frame, text=_T("establish"), height=45, corner_radius=2, font=("Consolas", 15, "bold"), fg_color="transparent", border_width=1, border_color="#00F0FF", text_color="#00F0FF", hover_color="#004455", command=self.submit_id).pack(pady=10, padx=50, fill="x")

        # Language Selector
        lang_frame = ctk.CTkFrame(self, fg_color="transparent")
        lang_frame.pack(side="bottom", pady=20)
        ctk.CTkLabel(lang_frame, text=_T("lang_label"), font=("Consolas", 12), text_color="#94A3B8").pack(side="left", padx=5)
        
        current_lang = config.load_config().get("lang", "en")
        lang_combo = ctk.CTkComboBox(lang_frame, values=["English", "中文"], width=100, font=("Consolas", 12), fg_color="#111726", border_color="#1E293B", button_color="#1E293B", text_color="#00F0FF")
        lang_combo.set("English" if current_lang == "en" else "中文")
        
        def change_lang(choice):
            config.save_config("lang", "en" if choice == "English" else "zh")
            self.show_id_selection()
        lang_combo.configure(command=change_lang)
        lang_combo.pack(side="left")

    def submit_id(self):
        uid = self.id_entry.get().strip()
        if not uid: return
        self.local_id = uid
        config.save_config("local_id", uid)
        self.show_role_selection()

    def show_role_selection(self):
        for widget in self.winfo_children():
            widget.destroy()
            
        self.configure(fg_color="#090C15")
        frame = ctk.CTkFrame(self, fg_color="#111726", corner_radius=2, border_width=1, border_color="#1E293B")
        frame.pack(pady=100, padx=50, fill="both", expand=True)
        
        ctk.CTkLabel(frame, text=f"{_T('auth')} {self.local_id}", font=("Consolas", 22, "bold"), text_color="#00FF9D").pack(pady=30)
        ctk.CTkLabel(frame, text=_T("uplink"), text_color="#64748B", font=("Consolas", 14)).pack(pady=10)
        
        ctk.CTkButton(frame, text=_T("host"), height=45, corner_radius=2, font=("Consolas", 15, "bold"), fg_color="transparent", border_width=1, border_color="#A23BFF", text_color="#A23BFF", hover_color="#441177", command=lambda: self.enter_room('host')).pack(pady=20, padx=50, fill="x")
        ctk.CTkButton(frame, text=_T("client"), height=45, corner_radius=2, font=("Consolas", 15, "bold"), fg_color="transparent", border_width=1, border_color="#00FF9D", text_color="#00FF9D", hover_color="#004433", command=lambda: self.enter_room('client')).pack(pady=10, padx=50, fill="x")

        # Settings
        ctk.CTkButton(self, text="< " + _T("exit_link").replace("< ", ""), width=100, font=("Consolas", 12), fg_color="transparent", border_width=1, border_color="#FF003C", text_color="#FF003C", hover_color="#550011", command=self.show_id_selection).pack(side="bottom", pady=20)


    def enter_room(self, role):
        for widget in self.winfo_children():
            widget.destroy()
            
        self.configure(fg_color="#090C15")
        self.ui_ctrl.build_top_bar()
        work_frame = ctk.CTkFrame(self, fg_color="transparent")
        work_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        if role == 'host':
            self.ui_ctrl.build_host_ui(work_frame)
        else:
            self.ui_ctrl.build_client_ui(work_frame)

    def on_closing(self):
        cfg = config.load_config()
        saved_action = cfg.get("close_action")
        
        if saved_action == "close":
            self._real_quit()
            return
        elif saved_action == "minimize":
            self.hide_window()
            return

        dialog = ctk.CTkToplevel(self)
        dialog.title("EXIT")
        dialog.geometry("400x180")
        dialog.transient(self)
        dialog.grab_set()
        dialog.configure(fg_color="#090C15")
        
        ctk.CTkLabel(dialog, text=_T("term"), font=("Consolas", 15, "bold"), text_color="#FF003C").pack(pady=(20, 5))
        
        remember_var = ctk.BooleanVar(value=False)
        chk = ctk.CTkCheckBox(dialog, text=_T("mem"), variable=remember_var, font=("Consolas", 11), fg_color="#00F0FF", border_color="#00F0FF", hover_color="#004455", text_color="#94A3B8")
        chk.pack(pady=(0, 15))
        
        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack()
        
        def do_close():
            if remember_var.get():
                config.save_config("close_action", "close")
            dialog.destroy()
            self._real_quit()
            
        def do_minimize():
            if remember_var.get():
                config.save_config("close_action", "minimize")
            dialog.destroy()
            self.hide_window()
            
        ctk.CTkButton(btn_frame, text=_T("min"), corner_radius=2, font=("Consolas", 12), fg_color="transparent", border_width=1, border_color="#00F0FF", text_color="#00F0FF", hover_color="#004455", command=do_minimize, width=170).pack(side="left", padx=10)
        ctk.CTkButton(btn_frame, text=_T("dest"), corner_radius=2, font=("Consolas", 12), fg_color="transparent", border_width=1, border_color="#FF003C", text_color="#FF003C", hover_color="#550011", command=do_close, width=170).pack(side="left", padx=10)

    def hide_window(self):
        self.withdraw()
        if self.tray_icon is None:
            image = Image.new('RGB', (64, 64), color=(43, 45, 48))
            draw = ImageDraw.Draw(image)
            draw.ellipse((16, 16, 48, 48), fill=(16, 185, 129))
            
            menu = pystray.Menu(
                pystray.MenuItem("Albireo P2P", self.show_window, default=True),
                pystray.MenuItem("Exit", self.quit_window)
            )
            self.tray_icon = pystray.Icon("albireo", image, "Albireo", menu)
            threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def show_window(self, icon, item):
        self.after(0, self.deiconify)

    def quit_window(self, icon, item):
        icon.stop()
        self.after(0, self._real_quit)

    def _real_quit(self):
        self.engine.shutdown()
        self.playback_mgr.shutdown()
        self.destroy()
