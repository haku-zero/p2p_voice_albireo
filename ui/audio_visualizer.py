import math
import tkinter as tk
import customtkinter as ctk
from ui.theme import *

class AudioVisualizer(ctk.CTkFrame):
    """
    轻量级音频实时动态波形图 (Dynamic Audio Spectrum Visualizer)。
    职责：
    1. 接收实时音频能量 (RMS) 采样；
    2. 基于多频段阻尼插值 (Lerp / Decay) 计算 8~10 根频谱柱高度；
    3. 采用银河星空配色 (星光青蓝至极光绿渐变) 渲染动态波形；
    4. 具备完善的生命周期管理，支持静音自动沉降与安全销毁。
    """
    def __init__(self, parent, width=110, height=26, bar_count=9, bg_color=FRAME_COLOR):
        super().__init__(parent, fg_color="transparent")
        self.width = width
        self.height = height
        self.bar_count = bar_count
        self.bg_color = bg_color
        
        self.canvas = tk.Canvas(
            self, width=self.width, height=self.height,
            bg=self.bg_color, highlightthickness=0, bd=0
        )
        self.canvas.pack(fill="both", expand=True)
        
        # 频谱柱高度状态 [0.0 ~ 1.0]
        self.bar_heights = [0.0] * self.bar_count
        self.target_heights = [0.0] * self.bar_count
        
        self._alive = True
        self._animation_scheduled = False
        self._draw_bars()

    def update_rms(self, rms):
        """传入实时 RMS 音频能量 (0 ~ 4000+)，转换为多频段波形目标值"""
        if not self._alive:
            return
            
        normalized = min(rms / 3500.0, 1.0)
        
        # 模拟自然频带能量分布 (中心频段饱满，两侧高低频谐波扩散)
        for i in range(self.bar_count):
            factor = math.sin((i + 1) / (self.bar_count + 1) * math.pi)
            jitter = 0.85 + 0.3 * math.sin(i * 1.7 + rms * 0.05)
            h = normalized * factor * jitter
            self.target_heights[i] = max(0.05, min(h, 1.0))
            
        if not self._animation_scheduled:
            self._schedule_tick()

    def set_muted(self):
        """静音时快速衰减为静息状态"""
        self.target_heights = [0.05] * self.bar_count

    def _schedule_tick(self):
        if not self._alive:
            return
        self._animation_scheduled = True
        self.after(30, self._animation_tick)

    def _animation_tick(self):
        if not self._alive:
            return
            
        has_motion = False
        for i in range(self.bar_count):
            target = self.target_heights[i]
            current = self.bar_heights[i]
            
            # Lerp 弹性阻尼：上升敏捷 (0.45)，下降柔和缓慢衰减 (0.15)
            speed = 0.45 if target > current else 0.15
            new_val = current + (target - current) * speed
            
            if abs(new_val - current) > 0.005:
                has_motion = True
            self.bar_heights[i] = max(0.04, min(new_val, 1.0))
            
        self._draw_bars()
        
        # 自然回落衰减
        for i in range(self.bar_count):
            self.target_heights[i] = max(0.04, self.target_heights[i] * 0.82)
            
        if has_motion or any(h > 0.06 for h in self.bar_heights):
            self._schedule_tick()
        else:
            self._animation_scheduled = False

    def _draw_bars(self):
        if not self._alive or not self.canvas.winfo_exists():
            return
            
        self.canvas.delete("all")
        spacing = 3
        total_spacing = spacing * (self.bar_count + 1)
        bar_width = max(2, (self.width - total_spacing) // self.bar_count)
        
        for i in range(self.bar_count):
            x0 = spacing + i * (bar_width + spacing)
            x1 = x0 + bar_width
            
            h_ratio = self.bar_heights[i]
            bar_h = max(2, int((self.height - 4) * h_ratio))
            y1 = self.height - 2
            y0 = y1 - bar_h
            
            # 颜色渐变逻辑：静息为暗星轨灰蓝，能量高时渐变为星光青与极光绿
            if h_ratio > 0.6:
                fill_color = SUCCESS  # #10B981
            elif h_ratio > 0.2:
                fill_color = PRIMARY  # #38BDF8
            else:
                fill_color = BORDER_COLOR  # #222D52
                
            self.canvas.create_rectangle(x0, y0, x1, y1, fill=fill_color, outline="")

    def destroy(self):
        self._alive = False
        super().destroy()
