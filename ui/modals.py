import asyncio
import customtkinter as ctk
from utils.i18n import get_text as _T
from ui.theme import *

def copy_to_clipboard(root, text, btn):
    root.clipboard_clear()
    root.clipboard_append(text)
    root.update()
    btn.configure(text=_T("copied"), fg_color=SUCCESS, text_color=BG_COLOR)
    root.after(2000, lambda: btn.configure(text=_T("copy_key"), fg_color="transparent", text_color=PRIMARY))

class HostWizard:
    def __init__(self, root, engine, loop, on_complete=None):
        self.root = root
        self.engine = engine
        self.loop = loop
        self.on_complete = on_complete

    def open(self):
        modal = ctk.CTkToplevel(self.root)
        modal.title(_T("wizard_host_title"))
        modal.geometry("600x550")
        modal.transient(self.root)
        modal.grab_set()
        modal.configure(fg_color=BG_COLOR)
        
        self.mode_var = ctk.StringVar(value="democracy")
        if self.engine.gov_mgr.network_mode is None:
            mode_frame = ctk.CTkFrame(modal, fg_color="transparent")
            mode_frame.pack(fill="x", padx=20, pady=(15, 0))
            ctk.CTkLabel(mode_frame, text="GOVERNANCE_MODE:", font=FONT_BOLD, text_color=SUCCESS).pack(side="left")
            ctk.CTkOptionMenu(mode_frame, variable=self.mode_var, values=["democracy", "archon"], font=FONT_MAIN, fg_color=FRAME_COLOR, button_color=PRIMARY, button_hover_color=PRIMARY_HOV, text_color=TEXT_COLOR, corner_radius=0).pack(side="left", padx=10)
            
        tabview = ctk.CTkTabview(modal, width=550, height=450, fg_color=BG_COLOR, segmented_button_fg_color=FRAME_COLOR, segmented_button_selected_color=PRIMARY, segmented_button_selected_hover_color=PRIMARY_HOV)
        tabview.pack(padx=10, pady=10, fill="both", expand=True)
        
        tab_auto = tabview.add("Auto (MQTT)")
        tab_manual = tabview.add("Manual (Offline)")
        
        # --- AUTO MODE ---
        ctk.CTkLabel(tab_auto, text="Share this Room Code with your peers:", font=FONT_BOLD, text_color=PRIMARY).pack(pady=(30, 10))
        room_var = ctk.StringVar()
        room_entry = ctk.CTkEntry(tab_auto, textvariable=room_var, width=250, font=("Inter", 24, "bold"), justify="center", placeholder_text="e.g. 8899")
        room_entry.pack(pady=10)
        
        auto_status_lbl = ctk.CTkLabel(tab_auto, text="Waiting to start...", font=FONT_MAIN, text_color=BORDER_COLOR)
        auto_status_lbl.pack(pady=20)
        
        btn_host = ctk.CTkButton(tab_auto, text="Start Listening", font=FONT_BOLD, corner_radius=0, fg_color="transparent", border_width=1, border_color=SUCCESS, text_color=SUCCESS, hover_color="#004433")
        btn_host.pack(pady=10)
        
        def start_host_auto():
            room_code = room_var.get().strip()
            if not room_code: return
            
            btn_host.configure(state="disabled")
            auto_status_lbl.configure(text="Listening for peers on MQTT...", text_color=SUCCESS)
            
            if self.engine.gov_mgr.network_mode is None:
                self.engine.gov_mgr.network_mode = self.mode_var.get()
                if self.engine.gov_mgr.network_mode == 'archon':
                    self.engine.gov_mgr.archon_id = self.root.local_id
            
            from infrastructure.signaling.mqtt_signaling import MQTTRelay
            self.relay = MQTTRelay(room_code, self.root.local_id)
            self.engine.room_code = room_code
            
            def on_offer(sdp_b64, sender):
                self.root.after(0, lambda: auto_status_lbl.configure(text=f"Connecting to {sender[:8]}...", text_color=SECONDARY))
                def done(ans_str, remote_id, err):
                    if err: return
                    self.relay.send_answer(sender, ans_str)
                    self.root.after(0, lambda: auto_status_lbl.configure(text=f"Linked with {remote_id[:8]}!", text_color=SUCCESS))
                    if self.on_complete:
                        self.root.after(0, lambda: self.on_complete(remote_id))
                asyncio.run_coroutine_threadsafe(self.engine.host_accept_offer(sdp_b64, done), self.loop)
                
            self.relay.on_offer_received = on_offer
            self.relay.start()
            
        btn_host.configure(command=start_host_auto)
        
        # --- MANUAL MODE ---
        ctk.CTkLabel(tab_manual, text=_T("phase1_host"), font=FONT_BOLD, text_color=PRIMARY).pack(pady=(5, 0), anchor="w", padx=10)
        offer_box = ctk.CTkTextbox(tab_manual, height=70, corner_radius=0, fg_color=FRAME_COLOR, border_color=PRIMARY, border_width=1, text_color=TEXT_COLOR, font=FONT_MAIN)
        offer_box.pack(fill="x", padx=10, pady=5)
        
        process_btn = ctk.CTkButton(tab_manual, text=_T("compute_ans"), font=FONT_BOLD, corner_radius=0, fg_color="transparent", border_width=1, border_color=SECONDARY, text_color=SECONDARY, hover_color=SECONDARY_HOV)
        process_btn.pack(pady=10)
        
        ctk.CTkLabel(tab_manual, text=_T("phase2_host"), font=FONT_BOLD, text_color=PRIMARY).pack(pady=(5, 0), anchor="w", padx=10)
        answer_box = ctk.CTkTextbox(tab_manual, height=70, corner_radius=0, fg_color=FRAME_COLOR, border_color=SECONDARY, border_width=1, text_color=TEXT_COLOR, font=FONT_MAIN)
        answer_box.pack(fill="x", padx=10, pady=5)
        
        copy_ans_btn = ctk.CTkButton(tab_manual, text=_T("copy_key"), width=120, font=FONT_BOLD, corner_radius=0, fg_color="transparent", border_width=1, border_color=PRIMARY, text_color=PRIMARY, state="disabled")
        copy_ans_btn.pack(pady=5)
        
        status_lbl = ctk.CTkLabel(tab_manual, text=_T("await_input"), font=FONT_MAIN, text_color=BORDER_COLOR)
        status_lbl.pack(pady=5)
        
        def process_manual():
            offer_str = offer_box.get("1.0", "end").strip()
            if not offer_str: return
            process_btn.configure(state="disabled")
            status_lbl.configure(text=_T("computing_keys"), text_color=SECONDARY)
            
            if self.engine.gov_mgr.network_mode is None:
                self.engine.gov_mgr.network_mode = self.mode_var.get()
                if self.engine.gov_mgr.network_mode == 'archon':
                    self.engine.gov_mgr.archon_id = self.root.local_id
            
            def done(ans_str, remote_id, err):
                if err:
                    status_lbl.configure(text=f"ERROR: {ans_str}", text_color=DANGER)
                    process_btn.configure(state="normal")
                    return
                answer_box.delete("1.0", "end")
                answer_box.insert("end", ans_str)
                copy_ans_btn.configure(state="normal", command=lambda: copy_to_clipboard(self.root, ans_str, copy_ans_btn))
                status_lbl.configure(text=f"{_T('link_est')} [{remote_id}].", text_color=SUCCESS)
                if self.on_complete:
                    self.root.after(0, lambda: self.on_complete(remote_id))
                
            asyncio.run_coroutine_threadsafe(self.engine.host_accept_offer(offer_str, done), self.loop)
            
        process_btn.configure(command=process_manual)


class ClientWizard:
    def __init__(self, root, engine, loop, on_complete=None):
        self.root = root
        self.engine = engine
        self.loop = loop
        self.on_complete = on_complete

    def open(self):
        modal = ctk.CTkToplevel(self.root)
        modal.title(_T("wizard_client_title"))
        modal.geometry("600x550")
        modal.transient(self.root)
        modal.grab_set()
        modal.configure(fg_color=BG_COLOR)
        
        tabview = ctk.CTkTabview(modal, width=550, height=450, fg_color=BG_COLOR, segmented_button_fg_color=FRAME_COLOR, segmented_button_selected_color=PRIMARY, segmented_button_selected_hover_color=PRIMARY_HOV)
        tabview.pack(padx=10, pady=10, fill="both", expand=True)
        
        tab_auto = tabview.add("Auto (MQTT)")
        tab_manual = tabview.add("Manual (Offline)")
        
        # --- AUTO MODE ---
        ctk.CTkLabel(tab_auto, text="Enter the Room Code to join:", font=FONT_BOLD, text_color=PRIMARY).pack(pady=(30, 10))
        room_var = ctk.StringVar()
        room_entry = ctk.CTkEntry(tab_auto, textvariable=room_var, width=250, font=("Inter", 24, "bold"), justify="center", placeholder_text="e.g. 8899")
        room_entry.pack(pady=10)
        
        auto_status_lbl = ctk.CTkLabel(tab_auto, text="Ready to connect...", font=FONT_MAIN, text_color=BORDER_COLOR)
        auto_status_lbl.pack(pady=20)
        
        btn_client = ctk.CTkButton(tab_auto, text="Join Room", font=FONT_BOLD, corner_radius=0, fg_color="transparent", border_width=1, border_color=SECONDARY, text_color=SECONDARY, hover_color=SECONDARY_HOV)
        btn_client.pack(pady=10)
        
        def start_client_auto():
            room_code = room_var.get().strip()
            if not room_code: return
            
            btn_client.configure(state="disabled")
            auto_status_lbl.configure(text="Generating cryptographic offer...", text_color=SECONDARY)
            
            from infrastructure.signaling.mqtt_signaling import MQTTRelay
            self.relay = MQTTRelay(room_code, self.root.local_id)
            self.engine.room_code = room_code
            self.relay.start()
            
            def on_answer(sdp_b64, sender):
                self.root.after(0, lambda: auto_status_lbl.configure(text=f"Finalizing with {sender[:8]}...", text_color=SUCCESS))
                def done(remote_id, err_msg):
                    if not err_msg:
                        if self.on_complete:
                            self.root.after(0, lambda: self.on_complete(remote_id))
                        self.relay.stop()
                        self.root.after(0, modal.destroy)
                asyncio.run_coroutine_threadsafe(self.engine.client_accept_answer(sdp_b64, done), self.loop)
                
            self.relay.on_answer_received = on_answer
            
            def offer_done(offer_str, err):
                if err: return
                self.root.after(0, lambda: auto_status_lbl.configure(text="Offer sent via MQTT. Waiting for Answer...", text_color=PRIMARY))
                self.relay.send_offer("all", offer_str)
                
            asyncio.run_coroutine_threadsafe(self.engine.client_generate_offer(offer_done), self.loop)
            
        btn_client.configure(command=start_client_auto)
        
        # --- MANUAL MODE ---
        gen_btn = ctk.CTkButton(tab_manual, text=_T("phase1_client"), font=FONT_BOLD, corner_radius=0, fg_color="transparent", border_width=1, border_color=SECONDARY, text_color=SECONDARY, hover_color=SECONDARY_HOV)
        gen_btn.pack(pady=10)
        
        offer_box = ctk.CTkTextbox(tab_manual, height=60, corner_radius=0, fg_color=FRAME_COLOR, border_color=SECONDARY, border_width=1, text_color=TEXT_COLOR, font=FONT_MAIN)
        offer_box.pack(fill="x", padx=10, pady=5)
        
        copy_offer_btn = ctk.CTkButton(tab_manual, text=_T("copy_key"), width=120, font=FONT_BOLD, corner_radius=0, fg_color="transparent", border_width=1, border_color=PRIMARY, text_color=PRIMARY, state="disabled")
        copy_offer_btn.pack(pady=5)
        
        ctk.CTkLabel(tab_manual, text=_T("phase2_client"), font=FONT_BOLD, text_color=PRIMARY).pack(pady=(10,0), anchor="w", padx=10)
        answer_box = ctk.CTkTextbox(tab_manual, height=60, corner_radius=0, fg_color=FRAME_COLOR, border_color=PRIMARY, border_width=1, text_color=TEXT_COLOR, font=FONT_MAIN)
        answer_box.pack(fill="x", padx=10, pady=5)
        
        conn_btn = ctk.CTkButton(tab_manual, text=_T("finalize"), font=FONT_BOLD, corner_radius=0, fg_color="transparent", border_width=1, border_color=SUCCESS, text_color=SUCCESS, hover_color="#004433")
        conn_btn.pack(pady=15)
        
        status_lbl = ctk.CTkLabel(tab_manual, text=_T("await_input"), font=FONT_MAIN, text_color=BORDER_COLOR)
        status_lbl.pack()
        
        def gen():
            gen_btn.configure(state="disabled")
            status_lbl.configure(text=_T("gen_keys"), text_color=SECONDARY)
            def done(offer_str, err):
                if err:
                    status_lbl.configure(text=f"ERROR: {offer_str}", text_color=DANGER)
                    gen_btn.configure(state="normal")
                    return
                offer_box.delete("1.0", "end")
                offer_box.insert("end", offer_str)
                copy_offer_btn.configure(state="normal", command=lambda: copy_to_clipboard(self.root, offer_str, copy_offer_btn))
                status_lbl.configure(text=_T("offer_ready"), text_color=SUCCESS)
            asyncio.run_coroutine_threadsafe(self.engine.client_generate_offer(done), self.loop)
            
        def conn():
            ans_str = answer_box.get("1.0", "end").strip()
            if not ans_str: return
            def done(remote_id, err_msg):
                if not err_msg:
                    if self.on_complete:
                        self.root.after(0, lambda: self.on_complete(remote_id))
                    self.root.after(0, lambda: modal.destroy())
                else:
                    self.root.after(0, lambda: status_lbl.configure(text=f"ERROR: {err_msg}", text_color=DANGER))
            asyncio.run_coroutine_threadsafe(self.engine.client_accept_answer(ans_str, done), self.loop)

        gen_btn.configure(command=gen)
        conn_btn.configure(command=conn)
