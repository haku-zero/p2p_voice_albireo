import asyncio
import json
import base64
import zlib
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaRelay
from core.audio_mixer import CustomMixerTrack
from core.file_transfer import FileTransferManager
from core.audio_io import start_playback_loop

class WebRTCEngine:
    def __init__(self, local_mic, playback_mgr, loop, update_ui_cb):
        self.local_mic = local_mic
        self.playback_mgr = playback_mgr
        self.loop = loop
        self.update_ui_cb = update_ui_cb
        self.relay = MediaRelay()
        self.connections = {}
        self.channels = {}
        self.poll_tasks = {}
        
        self.file_manager = FileTransferManager(self)
        self.mixer_tracks = {}
        self.is_host = False
        
        self.local_mic.on_level_callback = lambda rms: self.update_ui_cb("local_mic_level", rms=rms)
        self._mic_alive_task = asyncio.run_coroutine_threadsafe(self._keep_mic_alive(), self.loop)

    async def _keep_mic_alive(self):
        while True:
            if not self.connections:
                try:
                    await self.local_mic.recv()
                except Exception as e:
                    print(f"[Mic Alive Err] {e}")
                await asyncio.sleep(0.01)
            else:
                await asyncio.sleep(0.1)
                
    async def monitor_stats(self, pc, remote_id):
        while True:
            await asyncio.sleep(2)
            if pc.connectionState in ["closed", "failed"]:
                break
            if pc.connectionState != "connected":
                continue
            try:
                stats = await pc.getStats()
                ping_ms = 0
                for key, stat in stats.items():
                    if stat.type == "remote-inbound-rtp":
                        ping_ms = getattr(stat, "roundTripTime", 0) * 1000
                self.update_ui_cb("stats", member_id=remote_id, ping=int(ping_ms))
            except Exception:
                pass

    def _setup_datachannel(self, channel, initial_id):
        self.channels[initial_id] = channel
        
        @channel.on("open")
        def on_open():
            current_id = next((rid for rid, ch in self.channels.items() if ch == channel), initial_id)
            print(f"[DataChannel] Channel opened with {current_id}")
            
        @channel.on("message")
        def on_message(message):
            current_id = next((rid for rid, ch in self.channels.items() if ch == channel), initial_id)
            try:
                if isinstance(message, bytes):
                    message = message.decode('utf-8')
                data = json.loads(message)
                if data.get("type") == "chat":
                    sender = data.get("sender", current_id)
                    self.update_ui_cb("chat_message", member_id=sender, message=data["msg"])
                    
                    if self.is_host:
                        payload_bytes = json.dumps(data).encode('utf-8')
                        for rid, ch in self.channels.items():
                            if rid != current_id and ch.readyState == "open":
                                ch.send(payload_bytes)
            except Exception as e:
                print(f"[DataChannel] message decode error: {e}")

    def send_chat(self, msg, sender_id):
        payload_bytes = json.dumps({"type": "chat", "sender": sender_id, "msg": msg}).encode('utf-8')
        def _send_sync():
            try:
                for remote_id, channel in self.channels.items():
                    if channel.readyState == "open":
                        channel.send(payload_bytes)
            except Exception as e:
                print(f"[WebRTC Thread] Send Error: {e}")
        self.loop.call_soon_threadsafe(_send_sync)

    def send_file(self, filepath, sender_id):
        return self.file_manager.send_file(filepath, sender_id)

    def _setup_peer_connection(self, pc, remote_id):
        channel = pc.createDataChannel("chat", negotiated=True, id=1)
        self._setup_datachannel(channel, remote_id)
        
        file_channel = pc.createDataChannel("file", negotiated=True, id=2)
        self.file_manager.setup_channel(file_channel, remote_id)
        
        base_mic_track = self.relay.subscribe(self.local_mic)
        mixer_track = CustomMixerTrack(base_mic_track)
        self.mixer_tracks[pc] = mixer_track
        pc.addTrack(mixer_track)
        
        @pc.on("track")
        def on_track(track):
            if track.kind == "audio":
                def on_level(rms):
                    current_id = next((rid for rid, p in self.connections.items() if p == pc), remote_id)
                    self.update_ui_cb("talking", member_id=current_id, rms=rms)
                    
                def on_frame(data):
                    for p, m_track in self.mixer_tracks.items():
                        if p != pc:
                            m_track.push_remote_audio(pc, data)
                            
                start_playback_loop(track, self.playback_mgr, on_level, on_frame)
                
        @pc.on("connectionstatechange")
        async def on_connectionstatechange():
            current_id = next((rid for rid, p in self.connections.items() if p == pc), remote_id)
            if pc.connectionState == "connected":
                self.update_ui_cb("status", member_id=current_id, status="connected")
                if current_id not in self.poll_tasks:
                    self.poll_tasks[current_id] = asyncio.create_task(self.monitor_stats(pc, current_id))
            elif pc.connectionState in ["closed", "failed", "disconnected"]:
                if pc not in self.connections.values():
                    return
                    
                self.update_ui_cb("status", member_id=current_id, status="disconnected")
                if current_id in self.poll_tasks:
                    self.poll_tasks[current_id].cancel()
                    del self.poll_tasks[current_id]
                
                for m_track in self.mixer_tracks.values():
                    with m_track.lock:
                        m_track.source_buffers.pop(pc, None)
                    
                if current_id in self.connections:
                    if self.connections[current_id] in self.mixer_tracks:
                        del self.mixer_tracks[self.connections[current_id]]
                    del self.connections[current_id]
                    
                if pc.connectionState != "closed":
                    asyncio.create_task(pc.close())
                    
                if len(self.connections) == 0:
                    self.update_ui_cb("all_disconnected")

    async def host_accept_offer(self, offer_b64, local_id, callback):
        self.is_host = True
        try:
            raw_bytes = base64.b64decode(offer_b64.strip())
            try:
                dec_bytes = zlib.decompress(raw_bytes)
            except zlib.error:
                dec_bytes = raw_bytes
            sdp_dict = json.loads(dec_bytes.decode('utf-8'))
            remote_id = sdp_dict.get("user_id", f"Unknown_{len(self.connections)}")
            
            offer = RTCSessionDescription(sdp=sdp_dict["sdp"], type=sdp_dict["type"])
            pc = RTCPeerConnection()
            self.connections[remote_id] = pc
            self._setup_peer_connection(pc, remote_id)
            
            await pc.setRemoteDescription(offer)
            answer = await pc.createAnswer()
            await pc.setLocalDescription(answer)
            await asyncio.sleep(2)
            
            ans_dict = {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type, "user_id": local_id}
            ans_bytes = json.dumps(ans_dict).encode('utf-8')
            ans_b64 = base64.b64encode(zlib.compress(ans_bytes)).decode()
            callback(ans_b64, remote_id, False)
        except Exception as e:
            callback(str(e), None, True)

    async def client_generate_offer(self, local_id, callback):
        try:
            pc = RTCPeerConnection()
            self.connections['host'] = pc
            self._setup_peer_connection(pc, "host")
                
            offer = await pc.createOffer()
            await pc.setLocalDescription(offer)
            await asyncio.sleep(2)
            
            sdp_dict = {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type, "user_id": local_id}
            offer_bytes = json.dumps(sdp_dict).encode('utf-8')
            offer_b64 = base64.b64encode(zlib.compress(offer_bytes)).decode()
            callback(offer_b64, False)
        except Exception as e:
            callback(str(e), True)

    async def client_accept_answer(self, ans_b64, callback):
        try:
            raw_bytes = base64.b64decode(ans_b64.strip())
            try:
                dec_bytes = zlib.decompress(raw_bytes)
            except zlib.error:
                dec_bytes = raw_bytes
            sdp_dict = json.loads(dec_bytes.decode('utf-8'))
            remote_id = sdp_dict.get("user_id", "Host")
            
            answer = RTCSessionDescription(sdp=sdp_dict["sdp"], type=sdp_dict["type"])
            await self.connections['host'].setRemoteDescription(answer)
            
            pc = self.connections.pop('host')
            self.connections[remote_id] = pc
            
            if 'host' in self.channels:
                chan = self.channels.pop('host')
                self.channels[remote_id] = chan
                
            self.file_manager.rename_connection('host', remote_id)
            
            if 'host' in self.poll_tasks:
                task = self.poll_tasks.pop('host')
                self.poll_tasks[remote_id] = task

            callback(remote_id, False)
        except Exception as e:
            callback(str(e), True)

    def shutdown(self):
        if hasattr(self, '_mic_alive_task') and self._mic_alive_task:
            self._mic_alive_task.cancel()
        for task in self.poll_tasks.values():
            task.cancel()
        for pc in list(self.connections.values()):
            asyncio.run_coroutine_threadsafe(pc.close(), self.loop)

    def reset(self):
        self.shutdown()
        self.connections.clear()
        self.channels.clear()
        self.poll_tasks.clear()
        self.file_manager.clear()
        self.mixer_tracks.clear()
        self.is_host = False
        self._mic_alive_task = asyncio.run_coroutine_threadsafe(self._keep_mic_alive(), self.loop)
