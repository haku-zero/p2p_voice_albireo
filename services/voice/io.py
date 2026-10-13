import pyaudio
import numpy as np
import threading
import queue
import asyncio
from aiortc.mediastreams import MediaStreamTrack
from av import AudioFrame
import fractions

pyaudio_instance = pyaudio.PyAudio()

def get_audio_devices():
    inputs = {"Default": None}
    outputs = {"Default": None}
    
    # 获取 WASAPI 的 API index
    wasapi_idx = -1
    try:
        info = pyaudio_instance.get_host_api_info_by_type(pyaudio.paWASAPI)
        wasapi_idx = info.get('index', -1)
    except:
        pass

    for i in range(pyaudio_instance.get_device_count()):
        info = pyaudio_instance.get_device_info_by_index(i)
        
        api_name = "Unknown"
        try:
            api_info = pyaudio_instance.get_host_api_info_by_index(info['hostApi'])
            api_name = api_info.get('name', 'Unknown').replace("Windows ", "")
        except: pass
        
        prefix = f"[{api_name}] "
        name = info["name"]
        if info["maxInputChannels"] > 0:
            inputs[f"{prefix}{name}"] = i
        if info["maxOutputChannels"] > 0:
            outputs[f"{prefix}{name}"] = i
            
    return inputs, outputs


class PlaybackManager:
    def __init__(self):
        self.device_index = None
        self.stream = None
        self.volume = 0.1
        self.muted = False
        self._stream_lock = threading.Lock()
        self.open_stream()

    def open_stream(self):
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        # Windows speakers are almost always Stereo. WASAPI often fails silently if requested to play Mono.
        self.stream = pyaudio_instance.open(format=pyaudio.paInt16,
                                            channels=2,
                                            rate=48000,
                                            output=True,
                                            output_device_index=self.device_index)

    def change_device(self, idx):
        self.device_index = idx
        self.open_stream()

    def play_frame(self, data_bytes):
        if self.muted:
            return
            
        audio_arr = np.frombuffer(data_bytes, dtype=np.int16)
        if self.volume != 1.0:
            audio_arr = np.clip(audio_arr * self.volume, -32768, 32767).astype(np.int16)
        
        # Duplicate mono to stereo for safe playback
        stereo_arr = np.repeat(audio_arr, 2)
        data_bytes = stereo_arr.tobytes()
            
        try:
            with self._stream_lock:
                self.stream.write(data_bytes)
        except Exception as e:
            print(f"[Audio Output Error] {e}")

    def play_stereo_frame(self, data_bytes):
        if self.muted: return
        audio_arr = np.frombuffer(data_bytes, dtype=np.int16)
        if self.volume != 1.0:
            audio_arr = np.clip(audio_arr * self.volume, -32768, 32767).astype(np.int16)
        try:
            with self._stream_lock:
                self.stream.write(audio_arr.tobytes())
        except Exception as e:
            print(f"[Audio Output Error] {e}")

    def play_beep(self):
        if self.muted: return
        duration = 0.2
        f = 523.25
        t = np.arange(48000 * duration) / 48000.0
        samples = np.sin(2 * np.pi * f * t)
        envelope = np.exp(-t * 15)
        samples = samples * envelope
        samples = (samples * 32767 * self.volume * 0.4).astype(np.int16)
        # Duplicate mono to stereo
        stereo_samples = np.repeat(samples, 2)
        def _beep_write():
            try:
                with self._stream_lock:
                    self.stream.write(stereo_samples.tobytes())
            except Exception:
                pass
        threading.Thread(target=_beep_write).start()

    def shutdown(self):
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        pyaudio_instance.terminate()


class MicrophoneTrack(MediaStreamTrack):
    kind = "audio"

    def __init__(self, playback_mgr):
        super().__init__()
        self.playback_mgr = playback_mgr
        self.on_level_callback = None
        self.sample_rate = 48000
        self.samples_per_frame = 960  # 20ms
        self.device_index = None
        self.stream = None
        self.muted = False
        self.volume = 1.0
        self.noise_gate_threshold = 0
        self.channels = 1
        self.stream_lock = threading.Lock()
           # Smart VAD & Noise Gate 2.0 (Dual-threshold Hysteresis + Hangover Time)
        self.vad_enabled = True
        self.vad_attack_threshold = 300.0   # RMS threshold to trigger speech (was 450.0)
        self.vad_release_threshold = 150.0  # RMS threshold below which hangover countdown starts (was 220.0)
        self.vad_hangover_frames = 15      # 15 frames * 20ms = 300ms natural tail retention
        self._hangover_counter = 0
        self._voice_active = False
        
        # Audio queues and continuous pump thread
        self._audio_queue = queue.Queue(maxsize=10)
        self._webrtc_queue = queue.Queue(maxsize=10)
        self._running = False
        self._pump_thread = None
        
        self.open_stream()

    def open_stream(self):
        with self.stream_lock:
            self._running = False
            if self.stream:
                try:
                    self.stream.stop_stream()
                    self.stream.close()
                except: pass
                
            try:
                if self.device_index is None:
                    # 尝试寻找 WASAPI 的默认输入设备
                    try:
                        wasapi_info = pyaudio_instance.get_host_api_info_by_type(pyaudio.paWASAPI)
                        self.device_index = wasapi_info.get('defaultInputDevice')
                    except:
                        pass
                
                info = pyaudio_instance.get_device_info_by_index(self.device_index) if self.device_index is not None else pyaudio_instance.get_default_input_device_info()
                # 强制使用 48000 采样率
                self.sample_rate = 48000
                self.channels = min(int(info.get('maxInputChannels', 1)), 2)
                if self.channels == 0: self.channels = 1
                self.samples_per_frame = int(self.sample_rate * 0.02)
                
                # 清空队列
                while not self._audio_queue.empty():
                    try: self._audio_queue.get_nowait()
                    except queue.Empty: break
                while not self._webrtc_queue.empty():
                    try: self._webrtc_queue.get_nowait()
                    except queue.Empty: break
                
                def _audio_callback(in_data, frame_count, time_info, status):
                    try:
                        self._audio_queue.put_nowait(in_data)
                    except queue.Full:
                        try:
                            self._audio_queue.get_nowait()
                            self._audio_queue.put_nowait(in_data)
                        except:
                            pass
                    return (None, pyaudio.paContinue)
                
                self.stream = pyaudio_instance.open(format=pyaudio.paInt16,
                                                    channels=self.channels,
                                                    rate=self.sample_rate,
                                                    input=True,
                                                    input_device_index=self.device_index,
                                                    frames_per_buffer=self.samples_per_frame,
                                                    stream_callback=_audio_callback)
                self._running = True
                self._pump_thread = threading.Thread(target=self._pump_worker, daemon=True)
                self._pump_thread.start()
            except Exception as e:
                print(f"Open Error: {e}")
            self.pts = 0

    def close(self):
        self._running = False
        with self.stream_lock:
            if self.stream:
                try:
                    self.stream.stop_stream()
                    self.stream.close()
                except: pass

    def change_device(self, idx):
        self.device_index = idx
        self.open_stream()

    def clear_buffers(self):
        """Flushes all queued audio to guarantee instant silence upon muting."""
        while not self._audio_queue.empty():
            try:
                self._audio_queue.get_nowait()
            except queue.Empty:
                break
        while not self._webrtc_queue.empty():
            try:
                self._webrtc_queue.get_nowait()
            except queue.Empty:
                break

    def process_audio_frame(self, data):
        """
        Processes a raw PCM frame: calculates RMS, applies VAD hysteresis & hangover,
        and returns (processed_data, rms, is_active).
        """
        raw_rms = 0.0
        if len(data) > 0:
            raw_arr = np.frombuffer(data, dtype=np.int16).astype(np.float32)
            raw_rms = float(np.sqrt(np.mean(raw_arr**2)))

        is_silenced = False
        if self.muted:
            is_silenced = True
            self._voice_active = False
            self._hangover_counter = 0
        elif self.vad_enabled:
            if raw_rms >= self.vad_attack_threshold:
                self._voice_active = True
                self._hangover_counter = self.vad_hangover_frames
            elif self._voice_active:
                if raw_rms >= self.vad_release_threshold:
                    self._hangover_counter = self.vad_hangover_frames
                else:
                    self._hangover_counter -= 1
                    if self._hangover_counter <= 0:
                        self._voice_active = False
            if not self._voice_active:
                is_silenced = True
        elif self.noise_gate_threshold > 0 and raw_rms < self.noise_gate_threshold:
            is_silenced = True

        if is_silenced:
            data = b'\x00' * (self.samples_per_frame * 2)
            rms = 0.0
        else:
            rms = raw_rms
            if self.volume != 1.0 and len(data) > 0:
                arr = np.frombuffer(data, dtype=np.int16).astype(np.float32)
                arr = np.clip(arr * self.volume, -32768, 32767).astype(np.int16)
                data = arr.tobytes()

        return data, rms, self._voice_active

    def _pump_worker(self):
        """
        Continuous real-time pump thread:
        Pumps audio from PyAudio at 50Hz, calculates RMS, feeds local mic callbacks,
        and enqueues frames for WebRTC. Runs independently of whether WebRTC is polling.
        """
        while self._running:
            try:
                data = self._audio_queue.get(timeout=0.05)
            except queue.Empty:
                continue

            if not self._running:
                break
                
            if data is None:
                continue

            # 立体声下混频到单声道
            if self.channels == 2 and len(data) > 0:
                try:
                    arr = np.frombuffer(data, dtype=np.int16).reshape(-1, 2)
                    arr = arr.mean(axis=1).astype(np.int16)
                    data = arr.tobytes()
                except Exception:
                    data = b'\x00' * (self.samples_per_frame * 2)

            raw_rms = 0.0
            if len(data) > 0:
                raw_arr = np.frombuffer(data, dtype=np.int16).astype(np.float32)
                raw_rms = float(np.sqrt(np.mean(raw_arr**2)))

            if self.muted:
                level_to_report = 0.0
                processed_data = b'\x00' * (self.samples_per_frame * 2)
            else:
                processed_data, rms, _ = self.process_audio_frame(data)
                level_to_report = raw_rms

            # 触发实时音量计量（静音时强制上报 0.0，避免视觉波形或电平表跳动）
            if self.on_level_callback:
                try:
                    self.on_level_callback(level_to_report)
                except Exception:
                    pass

            # 触发本地帧回调（喂给 GlobalAudioMixer，静音时传递全 0 静音帧）
            if getattr(self, 'on_frame_callback', None):
                try:
                    self.on_frame_callback(processed_data)
                except Exception:
                    pass

            # 供 WebRTC recv() 消费
            try:
                self._webrtc_queue.put_nowait(processed_data)
            except queue.Full:
                try:
                    self._webrtc_queue.get_nowait()
                    self._webrtc_queue.put_nowait(processed_data)
                except:
                    pass

    async def recv(self):
        loop = asyncio.get_event_loop()
        try:
            def pop_queue():
                try:
                    return self._webrtc_queue.get(timeout=0.05)
                except queue.Empty:
                    return None
                    
            try:
                data = await loop.run_in_executor(None, pop_queue)
                if self.muted or data is None:
                    data = b'\x00' * (self.samples_per_frame * 2)
            except Exception as e:
                data = b'\x00' * (self.samples_per_frame * 2)
                
            expected_len = self.samples_per_frame * 2
            if len(data) != expected_len:
                if len(data) > expected_len:
                    data = data[:expected_len]
                else:
                    data = data + b'\x00' * (expected_len - len(data))
                    
            frame = AudioFrame(format='s16', layout='mono', samples=self.samples_per_frame)
            frame.planes[0].update(data)
            frame.sample_rate = self.sample_rate
            frame.pts = self.pts
            self.pts += self.samples_per_frame
            frame.time_base = fractions.Fraction(1, self.sample_rate)
            return frame
        except Exception as big_e:
            print(f"[Fatal Recv Err] {big_e}")
            raise big_e


def start_playback_loop(track, playback_mgr, on_audio_level, on_frame=None, play_local=True):
    import av
    resampler = av.AudioResampler(format='s16', layout='mono')
    
    async def play():
        loop = asyncio.get_event_loop()
        while True:
            try:
                frame = await track.recv()
                
                # IMPORTANT: Use AudioResampler to guarantee correct byte conversion for PyAudio
                # Without this, aiortc may return fltp or s16p, causing to_ndarray().tobytes() to generate invalid formats
                resampled_frames = resampler.resample(frame)
                if not resampled_frames:
                    continue
                frame = resampled_frames[0]
                data = frame.to_ndarray().tobytes()
                
                if on_frame:
                    on_frame(data)
                
                if play_local:
                    await loop.run_in_executor(None, playback_mgr.play_frame, data)
                
                arr = np.frombuffer(data, dtype=np.int16)
                rms = np.sqrt(np.mean(arr.astype(np.float32)**2))
                on_audio_level(rms)
            except Exception as e:
                print(f"[Playback Loop End] {e}")
                break
    asyncio.ensure_future(play())
