import customtkinter as ctk
from utils.i18n import get_text as _T
from utils import config
from ui.theme import *
from ui.store import store

class TopBarView:
    """
    顶部控制栏组件 (Top Bar Control View)。
    职责：
    1. 管理音频输入/输出硬件设备切换；
    2. 管理麦克风、扬声器音量及静音状态；
    3. 管理 PTT (按住说话) 与 Open Mic (常开) 模式切换及按键交互；
    4. 提供快捷功能：退出房间、NAT设置弹窗、解散房间（Host）、展开聊天面板。
    """
    def __init__(self, parent, media_ctrl, core_api, gov_api, chat_view, on_exit):
        self.parent = parent
        self.media_ctrl = media_ctrl
        self.core_api = core_api
        self.gov_api = gov_api
        self.chat_view = chat_view
        self.on_exit = on_exit
        self._alive = True
        
        self.container = ctk.CTkFrame(self.parent, fg_color="transparent")
        self.container.pack(fill="x", padx=10, pady=5)
        
        self._build_row0_actions()
        self._build_row1_devices()
        self._build_row2_controls()
        
        # 订阅 Store 数据流变更（单向绑定）
        store.subscribe(self._on_store_changed)

    def _build_row0_actions(self):
        row0 = ctk.CTkFrame(self.container, fg_color="transparent")
        row0.pack(fill="x", pady=(0, 5))
        
        ctk.CTkButton(
            row0, text=_T("exit_link"), width=120, font=FONT_BOLD, corner_radius=0,
            fg_color="transparent", border_width=1, border_color=DANGER,
            text_color=DANGER, hover_color=DANGER_HOV, command=self.on_exit
        ).pack(side="left")
        
        from ui.network_settings import NetworkSettingsModal
        net_btn = ctk.CTkButton(
            row0, text="[ NAT Settings ]", width=120, font=FONT_BOLD, corner_radius=0,
            fg_color="transparent", border_width=1, border_color=PRIMARY,
            text_color=PRIMARY, hover_color=PRIMARY_HOV, command=NetworkSettingsModal(self.parent).open
        )
        net_btn.pack(side="right", padx=10)
        
        if getattr(self.core_api._engine, "is_host", False):
            ctk.CTkButton(
                row0, text="[ Disband Room ]", width=120, font=FONT_BOLD, corner_radius=0,
                fg_color="transparent", border_width=1, border_color=DANGER,
                text_color=DANGER, hover_color=DANGER_HOV, command=self.gov_api.issue_end_room
            ).pack(side="left", padx=10)

    def _build_row1_devices(self):
        row1 = ctk.CTkFrame(self.container, fg_color="transparent")
        row1.pack(fill="x", pady=2)
        
        ctk.CTkLabel(row1, text=_T("audio_in"), font=FONT_MAIN, text_color=TEXT_COLOR).pack(side="left", padx=2)
        self.in_combo = ctk.CTkComboBox(
            row1, values=list(self.media_ctrl.inputs_map.keys()), command=self.media_ctrl.change_in_device,
            width=220, font=FONT_MAIN, fg_color=FRAME_COLOR, border_color=BORDER_COLOR,
            button_color=BORDER_COLOR, button_hover_color=PRIMARY, text_color=PRIMARY
        )
        self.in_combo.pack(side="left", padx=5)
        
        ctk.CTkLabel(row1, text=_T("audio_out"), font=FONT_MAIN, text_color=TEXT_COLOR).pack(side="left", padx=(15, 2))
        self.out_combo = ctk.CTkComboBox(
            row1, values=list(self.media_ctrl.outputs_map.keys()), command=self.media_ctrl.change_out_device,
            width=220, font=FONT_MAIN, fg_color=FRAME_COLOR, border_color=BORDER_COLOR,
            button_color=BORDER_COLOR, button_hover_color=PRIMARY, text_color=PRIMARY
        )
        self.out_combo.pack(side="left", padx=5)
        
        # 恢复已保存的音频设备
        cfg = config.load_config()
        saved_in = cfg.get("in_device")
        in_names = list(self.media_ctrl.inputs_map.keys())
        if saved_in not in in_names and in_names:
            saved_in = in_names[0]
        if saved_in:
            self.in_combo.set(saved_in)
            self.media_ctrl.change_in_device(saved_in)
            
        saved_out = cfg.get("out_device")
        out_names = list(self.media_ctrl.outputs_map.keys())
        if saved_out not in out_names and out_names:
            saved_out = out_names[0]
        if saved_out:
            self.out_combo.set(saved_out)
            self.media_ctrl.change_out_device(saved_out)
            
        config.save_config("in_device", saved_in)
        config.save_config("out_device", saved_out)

    def _build_row2_controls(self):
        row2 = ctk.CTkFrame(self.container, fg_color="transparent")
        row2.pack(fill="x", pady=8)
        
        # 麦克风开关
        self.mic_btn = ctk.CTkButton(
            row2, text=_T("mic_on"), font=FONT_BOLD, width=100, corner_radius=0,
            fg_color="transparent", border_width=1, border_color=PRIMARY,
            text_color=PRIMARY, hover_color=PRIMARY_HOV, command=self.media_ctrl.toggle_mic
        )
        self.mic_btn.pack(side="left", padx=2)
        
        # 麦克风增益滑块
        self.mic_vol_slider = ctk.CTkSlider(
            row2, from_=0, to=1.0, width=80, command=self.media_ctrl.change_mic_volume,
            button_color=PRIMARY, button_hover_color=PRIMARY_HOV, progress_color=PRIMARY
        )
        saved_mic_vol = config.load_config().get("mic_vol", 1.0)
        self.mic_vol_slider.set(saved_mic_vol)
        self.media_ctrl.change_mic_volume(saved_mic_vol)
        self.mic_vol_slider.pack(side="left", padx=5)
        
        # 音频实时动态波形图 (Audio Visualizer)
        from ui.audio_visualizer import AudioVisualizer
        self.visualizer = AudioVisualizer(row2, width=90, height=26, bar_count=8)
        self.visualizer.pack(side="left", padx=5)
        
        from utils.events import event_bus
        self._on_mic_level = lambda rms: self.parent.after(0, self.visualizer.update_rms, rms) if self._alive else None
        event_bus.on("local_mic_level", self._on_mic_level)
        
        # 麦克风模式选择 (Open Mic vs PTT)
        self.mic_mode_menu = ctk.CTkOptionMenu(
            row2, values=[_T("open_mic"), _T("ptt")], font=FONT_MAIN, command=self.change_mic_mode,
            width=160, fg_color=FRAME_COLOR, button_color=PRIMARY, button_hover_color=PRIMARY_HOV, text_color=PRIMARY
        )
        saved_mic_mode = config.load_config().get("mic_mode", _T("open_mic"))
        self.mic_mode_menu.set(saved_mic_mode)
        self.mic_mode_menu.pack(side="left", padx=5)
        
        # PTT 按钮
        self.ptt_btn = ctk.CTkButton(
            row2, text=_T("ptt_stdby"), font=FONT_BOLD, width=120, corner_radius=0,
            fg_color="transparent", border_width=1, border_color=BORDER_COLOR,
            text_color=BORDER_COLOR, state="disabled"
        )
        self.ptt_btn.pack(side="left", padx=5)
        self.ptt_btn.bind("<ButtonPress-1>", self._ptt_press)
        self.ptt_btn.bind("<ButtonRelease-1>", self._ptt_release)
        
        # 扬声器开关
        self.speaker_btn = ctk.CTkButton(
            row2, text=_T("spk_on"), font=FONT_BOLD, width=100, corner_radius=0,
            fg_color="transparent", border_width=1, border_color=SECONDARY,
            text_color=SECONDARY, hover_color=SECONDARY_HOV, command=self.media_ctrl.toggle_speaker
        )
        self.speaker_btn.pack(side="left", padx=(15, 2))
        
        # 扬声器音量滑块
        self.vol_slider = ctk.CTkSlider(
            row2, from_=0, to=1.0, width=100, command=self.media_ctrl.change_speaker_volume,
            button_color=SECONDARY, button_hover_color=SECONDARY_HOV, progress_color=SECONDARY
        )
        saved_spk_vol = config.load_config().get("speaker_vol", 0.1)
        self.vol_slider.set(saved_spk_vol)
        self.media_ctrl.change_speaker_volume(saved_spk_vol)
        self.vol_slider.bind("<ButtonRelease-1>", lambda e: self.media_ctrl.playback_mgr.play_beep())
        self.vol_slider.pack(side="left", padx=5)
        
        # 聊天面板唤起按钮
        self.chat_btn = ctk.CTkButton(
            row2, text=_T("chat"), font=FONT_BOLD, width=120, corner_radius=0,
            fg_color="transparent", border_width=1, border_color=PRIMARY,
            text_color=PRIMARY, hover_color=PRIMARY_HOV, command=self.chat_view.open
        )
        self.chat_btn.pack(side="right", padx=10)
        self.chat_view.chat_btn = self.chat_btn
        
        # 控件全部装配完成后，再执行麦克风模式初态配置
        self.change_mic_mode(saved_mic_mode)

    def change_mic_mode(self, mode):
        res = self.media_ctrl.change_mic_mode(mode)
        if getattr(self, 'ptt_btn', None) and self.ptt_btn.winfo_exists():
            if res == "ptt":
                self.ptt_btn.configure(state="normal", text=_T("hold_tx"), border_color=PRIMARY, text_color=PRIMARY)
            else:
                self.ptt_btn.configure(state="disabled", text=_T("ptt_stdby"), border_color=BORDER_COLOR, text_color=BORDER_COLOR)
        if getattr(self, 'mic_btn', None) and self.mic_btn.winfo_exists():
            if res == "ptt":
                self.mic_btn.configure(state="disabled", text=_T("mic_lock"), border_color=BORDER_COLOR, text_color=BORDER_COLOR)
            else:
                self.mic_btn.configure(state="normal", text=_T("mic_on"), border_color=PRIMARY, text_color=PRIMARY)

    def _ptt_press(self, event):
        if getattr(self, 'ptt_btn', None) and self.ptt_btn.winfo_exists() and self.ptt_btn.cget("state") == "normal":
            self.media_ctrl.handle_ptt(True)
            self.ptt_btn.configure(fg_color=SUCCESS, text_color=BG_COLOR, text=_T("tx_active"))

    def _ptt_release(self, event):
        if getattr(self, 'ptt_btn', None) and self.ptt_btn.winfo_exists() and self.ptt_btn.cget("state") == "normal":
            self.media_ctrl.handle_ptt(False)
            self.ptt_btn.configure(fg_color="transparent", text_color=PRIMARY, text=_T("hold_tx"))

    def _on_store_changed(self, state):
        if not self._alive:
            return
            
        # 响应麦克风静音状态变更
        if getattr(self, 'mic_btn', None) and self.mic_btn.winfo_exists():
            if state.get("mic_muted"):
                self.mic_btn.configure(text=_T("mic_muted"), border_color=DANGER, text_color=DANGER)
                if hasattr(self, 'visualizer'):
                    self.visualizer.set_muted()
            else:
                self.mic_btn.configure(text=_T("mic_on"), border_color=PRIMARY, text_color=PRIMARY)
                
        # 响应扬声器静音状态变更
        if getattr(self, 'speaker_btn', None) and self.speaker_btn.winfo_exists():
            if state.get("speaker_muted"):
                self.speaker_btn.configure(text=_T("spk_muted"), border_color=DANGER, text_color=DANGER)
            else:
                self.speaker_btn.configure(text=_T("spk_on"), border_color=SECONDARY, text_color=SECONDARY)

    def destroy(self):
        self._alive = False
        store.unsubscribe(self._on_store_changed)
        if getattr(self, 'visualizer', None):
            self.visualizer.destroy()
        if getattr(self, 'container', None) and self.container.winfo_exists():
            self.container.destroy()
