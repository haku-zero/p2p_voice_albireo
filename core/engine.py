import asyncio
import json
import base64
import zlib
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaRelay
from core.audio_mixer import CustomMixerTrack, GlobalAudioMixer
from core.file_transfer import FileTransferManager
from core.audio_io import start_playback_loop
from core.crypto import CryptoManager
from core.video_io import DynamicVideoTrack, start_video_receive_loop
from core.chat import ChatManager
from core.governance import GovernanceManager
from utils.events import event_bus

class WebRTCEngine:
    def __init__(self, local_mic, playback_mgr, loop):
        self.local_mic = local_mic
        self.playback_mgr = playback_mgr
        self.loop = loop
        self.relay = MediaRelay()
        self.connections = {}
        self.channels = {}
        self.poll_tasks = {}
        
        self.file_manager = FileTransferManager(self)
        self.mixer_tracks = {}
        self.global_mixer = GlobalAudioMixer(self.playback_mgr)
        self.global_mixer.start(self.loop)
        self.is_host = False
        self.chat_seen = set()
        
        self.crypto = CryptoManager()
        self.local_id = self.crypto.get_public_key()
        self.callsign = "Unknown"
        self.callsign_map = {self.local_id: self.callsign}
        
        self.local_video = DynamicVideoTrack()
        
        self.gov_mgr = GovernanceManager(self)
        self.chat_mgr = ChatManager(self)
        
        self.local_mic.on_level_callback = lambda rms: event_bus.emit("local_mic_level", rms)
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
                event_bus.emit("stats", remote_id, int(ping_ms))
            except Exception:
                pass

    def _setup_datachannel(self, channel, initial_id):
        self.channels[initial_id] = channel
        
        @channel.on("open")
        def on_open():
            current_id = next((rid for rid, ch in self.channels.items() if ch == channel), initial_id)
            print(f"[DataChannel] Channel opened with {current_id}")
            if self.gov_mgr.network_mode is not None:
                meta = {
                    "type": "sync_net_meta",
                    "sender": self.local_id,
                    "callsign": self.callsign,
                    "mode": self.gov_mgr.network_mode,
                    "archon_id": self.gov_mgr.archon_id,
                    "banned_list": list(self.gov_mgr.banned_list)
                }
                meta = self.crypto.sign_payload(meta)
                channel.send(json.dumps(meta).encode('utf-8'))
            
        @channel.on("message")
        def on_message(message):
            current_id = next((rid for rid, ch in self.channels.items() if ch == channel), initial_id)
            if self.gov_mgr.is_banned(current_id):
                return
            try:
                if isinstance(message, bytes):
                    message = message.decode('utf-8')
                data = json.loads(message)
                
                # Check signature
                sender = data.get("sender")
                if sender and not self.crypto.verify_payload(data, sender):
                    print(f"[Crypto] Dropped spoofed payload from {sender}")
                    return
                
                if "callsign" in data and sender:
                    self.callsign_map[sender] = data["callsign"]
                
                # Emit for decoupled managers (Chat, Governance)
                event_bus.emit("network_message_received", data, current_id)
                
                if data.get("type") == "peer_joined":
                    new_peer = data.get("peer_id")
                    if not self.is_host and new_peer not in self.connections:
                        asyncio.run_coroutine_threadsafe(self._initiate_mesh(new_peer), self.loop)
                        
                elif data.get("type") == "signaling":
                    target = data.get("target")
                    if target == getattr(self, "local_id", None) or target == "all":
                        sender = data.get("sender")
                        sdp = data.get("sdp")
                        sdp_type = data.get("sdp_type")
                        asyncio.run_coroutine_threadsafe(self._handle_mesh_signaling(sender, sdp, sdp_type), self.loop)
                    elif self.is_host and target in self.channels:
                        if self.channels[target].readyState == "open":
                            self.channels[target].send(message)
                            
            except Exception as e:
                print(f"[DataChannel] message decode error: {e}")

    def send_file(self, filepath, sender_id):
        return self.file_manager.send_file(filepath, sender_id)

    async def _initiate_mesh(self, peer_id):
        pc = RTCPeerConnection()
        self.connections[peer_id] = pc
        self._setup_peer_connection(pc, peer_id)
        
        offer = await pc.createOffer()
        await pc.setLocalDescription(offer)
        await asyncio.sleep(1.5)
        
        msg = json.dumps({
            "type": "signaling",
            "target": peer_id,
            "sender": getattr(self, "local_id", "Unknown"),
            "sdp": pc.localDescription.sdp,
            "sdp_type": pc.localDescription.type
        })
        for ch in self.channels.values():
            if ch.readyState == "open":
                ch.send(msg)

    async def _handle_mesh_signaling(self, sender, sdp, sdp_type):
        if sdp_type == "offer":
            pc = RTCPeerConnection()
            self.connections[sender] = pc
            self._setup_peer_connection(pc, sender)
            
            desc = RTCSessionDescription(sdp=sdp, type=sdp_type)
            await pc.setRemoteDescription(desc)
            
            answer = await pc.createAnswer()
            await pc.setLocalDescription(answer)
            await asyncio.sleep(1.5)
            
            msg = json.dumps({
                "type": "signaling",
                "target": sender,
                "sender": getattr(self, "local_id", "Unknown"),
                "sdp": pc.localDescription.sdp,
                "sdp_type": pc.localDescription.type
            })
            for ch in self.channels.values():
                if ch.readyState == "open":
                    ch.send(msg)
                    
        elif sdp_type == "answer":
            if sender in self.connections:
                pc = self.connections[sender]
                desc = RTCSessionDescription(sdp=sdp, type=sdp_type)
                await pc.setRemoteDescription(desc)

    def _setup_peer_connection(self, pc, remote_id):
        channel = pc.createDataChannel("chat", negotiated=True, id=1)
        self._setup_datachannel(channel, remote_id)
        
        file_channel = pc.createDataChannel("file", negotiated=True, id=2)
        self.file_manager.setup_channel(file_channel, remote_id)
        
        base_mic_track = self.relay.subscribe(self.local_mic)
        pc.addTrack(base_mic_track)
        pc.addTrack(self.local_video)
        
        @pc.on("track")
        def on_track(track):
            if track.kind == "audio":
                current_id = next((rid for rid, p in self.connections.items() if p == pc), remote_id)
                def on_level(rms):
                    event_bus.emit("talking", current_id, rms)
                    
                def on_frame(data):
                    self.global_mixer.push_remote_audio(current_id, data)
                            
                start_playback_loop(track, self.playback_mgr, on_level, on_frame, play_local=False)
            elif track.kind == "video":
                current_id = next((rid for rid, p in self.connections.items() if p == pc), remote_id)
                def on_video_frame(arr):
                    event_bus.emit("video_frame", current_id, arr)
                start_video_receive_loop(track, on_video_frame)
                
        @pc.on("connectionstatechange")
        async def on_connectionstatechange():
            current_id = next((rid for rid, p in self.connections.items() if p == pc), remote_id)
            if pc.connectionState == "connected":
                event_bus.emit("status", current_id, "connected")
                if current_id not in self.poll_tasks:
                    self.poll_tasks[current_id] = asyncio.create_task(self.monitor_stats(pc, current_id))
                if getattr(self, "is_host", False):
                    msg_dict = {"type": "peer_joined", "sender": self.local_id, "callsign": self.callsign, "peer_id": current_id}
                    msg_dict = self.crypto.sign_payload(msg_dict)
                    msg = json.dumps(msg_dict)
                    for rid, ch in self.channels.items():
                        if rid != current_id and ch.readyState == "open":
                            ch.send(msg)
            elif pc.connectionState in ["closed", "failed", "disconnected"]:
                if pc not in self.connections.values():
                    return
                    
                event_bus.emit("status", current_id, "disconnected")
                if current_id in self.poll_tasks:
                    self.poll_tasks[current_id].cancel()
                    del self.poll_tasks[current_id]
                
                self.global_mixer.remove_source(current_id)
                
                for m_track in self.mixer_tracks.values():
                    with m_track.lock:
                        m_track.source_buffers.pop(pc, None)
                    
                if current_id in self.connections:
                    if self.connections[current_id] in self.mixer_tracks:
                        del self.mixer_tracks[self.connections[current_id]]
                    del self.connections[current_id]
                    
                if current_id in self.channels:
                    del self.channels[current_id]
                self.file_manager.remove_connection(current_id)
                self.gov_mgr.on_peer_disconnected(current_id)
                    
                if pc.connectionState != "closed":
                    asyncio.create_task(pc.close())
                    
                if len(self.connections) == 0:
                    event_bus.emit("all_disconnected")

    async def host_accept_offer(self, offer_b64, callback):
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
            
            ans_dict = {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type, "user_id": self.local_id, "callsign": self.callsign}
            ans_bytes = json.dumps(ans_dict).encode('utf-8')
            ans_b64 = base64.b64encode(zlib.compress(ans_bytes)).decode()
            callback(ans_b64, remote_id, False)
        except Exception as e:
            callback(str(e), None, True)

    async def client_generate_offer(self, callback):
        try:
            pc = RTCPeerConnection()
            self.connections['host'] = pc
            self._setup_peer_connection(pc, "host")
                
            offer = await pc.createOffer()
            await pc.setLocalDescription(offer)
            await asyncio.sleep(2)
            
            sdp_dict = {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type, "user_id": self.local_id, "callsign": self.callsign}
            offer_bytes = json.dumps(sdp_dict).encode('utf-8')
            offer_b64 = base64.b64encode(zlib.compress(offer_bytes)).decode()
            callback(offer_b64, False)
        except Exception as e:
            callback(str(e), True)

    def toggle_screen_share(self):
        if self.local_video.sharing:
            self.local_video.stop_share()
            return False
        else:
            self.local_video.start_share()
            return True

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
        self.global_mixer.stop()
        async def _shutdown():
            if hasattr(self, '_mic_alive_task') and self._mic_alive_task:
                self._mic_alive_task.cancel()
            for task in self.poll_tasks.values():
                task.cancel()
            
            close_tasks = []
            for pc in list(self.connections.values()):
                close_tasks.append(pc.close())
            if close_tasks:
                await asyncio.gather(*close_tasks, return_exceptions=True)
                
            # Allow time for aiortc internals to clean up (like RTCIceTransport._monitor)
            await asyncio.sleep(0.1)
            
        future = asyncio.run_coroutine_threadsafe(_shutdown(), self.loop)
        try:
            future.result(timeout=3)
        except Exception:
            pass

    def reset(self):
        self.shutdown()
        self.connections.clear()
        self.channels.clear()
        self.poll_tasks.clear()
        self.file_manager.clear()
        self.mixer_tracks.clear()
        self.is_host = False
        self._mic_alive_task = asyncio.run_coroutine_threadsafe(self._keep_mic_alive(), self.loop)
