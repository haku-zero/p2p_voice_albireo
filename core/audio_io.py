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
        
        # 使用 Queue 和 Callback 模式彻底解决底层阻塞漏线程问题
        self._audio_queue = queue.Queue(maxsize=10)
        
        self.open_stream()

    def open_stream(self):
        with self.stream_lock:
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
                # 强制使用 48000 采样率！因为 WebRTC 的 Opus 编码器不支持 44100，会导致完全发不出声音！
                # 即使麦克风硬件是 44100，PyAudio 也会在底层通过 PortAudio 自动帮我们重采样为 48000。
                self.sample_rate = 48000
                self.channels = min(int(info.get('maxInputChannels', 1)), 2)
                if self.channels == 0: self.channels = 1
                self.samples_per_frame = int(self.sample_rate * 0.02)
                
                # 清空队列
                while not self._audio_queue.empty():
                    self._audio_queue.get_nowait()
                
                def _audio_callback(in_data, frame_count, time_info, status):
                    try:
                        self._audio_queue.put_nowait(in_data)
                    except queue.Full:
                        pass
                    return (None, pyaudio.paContinue)
                
                self.stream = pyaudio_instance.open(format=pyaudio.paInt16,
                                                    channels=self.channels,
                                                    rate=self.sample_rate,
                                                    input=True,
                                                    input_device_index=self.device_index,
                                                    frames_per_buffer=self.samples_per_frame,
                                                    stream_callback=_audio_callback)
            except Exception as e:
                print(f"Open Error: {e}")
            self.pts = 0

    def change_device(self, idx):
        self.device_index = idx
        self.open_stream()

    async def recv(self):
        loop = asyncio.get_event_loop()
        
        try:
            # 从队列中提取数据，最多等待 0.05 秒。如果超时，说明 OS 根本没给数据！
            def pop_queue():
                try:
                    return self._audio_queue.get(timeout=0.05)
                except queue.Empty:
                    return None
                    
            try:
                data = await loop.run_in_executor(None, pop_queue)
                if data is None:
                    data = b'\x00' * (self.samples_per_frame * 2 * self.channels)
            except Exception as e:
                print(f"Queue Read Error: {e}")
                data = b'\x00' * (self.samples_per_frame * 2 * self.channels)
                
            # 立体声下混频到单声道
            if self.channels == 2 and len(data) > 0:
                try:
                    arr = np.frombuffer(data, dtype=np.int16).reshape(-1, 2)
                    arr = arr.mean(axis=1).astype(np.int16)
                    data = arr.tobytes()
                except Exception as e:
                    print(f"Downmix Error: {e}")
                    data = b'\x00' * (self.samples_per_frame * 2)
                
            is_silenced = False
            
            # 麦克风物理静音 (按住说话模式也会通过此变量控制)
            if self.muted:
                is_silenced = True
                
            # 噪音门限
            elif self.noise_gate_threshold > 0 and len(data) > 0:
                arr = np.frombuffer(data, dtype=np.int16).astype(np.float32)
                rms = np.sqrt(np.mean(arr**2))
                if rms < self.noise_gate_threshold:
                    is_silenced = True
                    
            if is_silenced:
                data = b'\x00' * (self.samples_per_frame * 2)
                rms = 0.0
            else:
                arr = np.frombuffer(data, dtype=np.int16).astype(np.float32)
                rms = np.sqrt(np.mean(arr**2))
                if self.volume != 1.0:
                    arr = np.clip(arr * self.volume, -32768, 32767).astype(np.int16)
                    data = arr.tobytes()
                    
            if self.on_level_callback:
                self.on_level_callback(rms)
                
            # 这里是修复长度不匹配的关键！
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
