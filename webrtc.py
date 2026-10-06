import asyncio
import json
import base64
import zlib
from aiortc import RTCPeerConnection, RTCSessionDescription
from audio import start_playback_loop

class WebRTCEngine:
    def __init__(self, local_mic, playback_mgr, loop, update_ui_cb):
        self.local_mic = local_mic
        self.playback_mgr = playback_mgr
        self.loop = loop
        self.update_ui_cb = update_ui_cb
        self.connections = {}  # remote_id -> pc
        self.channels = {}     # remote_id -> datachannel
        self.poll_tasks = {}   
        
        self.file_channels = {}
        self.file_buffers = {}
        self.file_metadata = {}
        
        self.local_mic.on_level_callback = lambda rms: self.update_ui_cb("local_mic_level", rms=rms)
        # 必须使用 threadsafe 调度！否则因为不在同一线程，这个死循环任务永远不会被执行！
        asyncio.run_coroutine_threadsafe(self._keep_mic_alive(), self.loop)

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
            # Reverse lookup to get the latest ID if it was renamed
            current_id = next((rid for rid, ch in self.channels.items() if ch == channel), initial_id)
            print(f"[DataChannel] Channel opened with {current_id}")
            
        @channel.on("message")
        def on_message(message):
            current_id = next((rid for rid, ch in self.channels.items() if ch == channel), initial_id)
            print(f"[DataChannel] Received raw message from {current_id}: {message}")
            try:
                if isinstance(message, bytes):
                    message = message.decode('utf-8')
                data = json.loads(message)
                if data.get("type") == "chat":
                    self.update_ui_cb("chat_message", member_id=current_id, message=data["msg"])
            except Exception as e:
                print(f"[DataChannel] message decode error: {e}")

    def _setup_filechannel(self, channel, initial_id):
        self.file_channels[initial_id] = channel
        self.file_buffers[initial_id] = bytearray()
        self.file_metadata[initial_id] = None
        
        @channel.on("message")
        def on_message(message):
            current_id = next((rid for rid, ch in self.file_channels.items() if ch == channel), initial_id)
            if isinstance(message, str):
                try:
                    meta = json.loads(message)
                    if meta.get("type") == "file_meta":
                        self.file_metadata[current_id] = meta
                        self.file_buffers[current_id] = bytearray()
                        self.update_ui_cb("file_incoming", member_id=current_id, filename=meta["name"], size=meta["size"])
                    elif meta.get("type") == "file_done":
                        with open(self.file_metadata[current_id]["name"], "wb") as f:
                            f.write(self.file_buffers[current_id])
                        self.update_ui_cb("file_done", member_id=current_id, filename=self.file_metadata[current_id]["name"])
                except Exception as e:
                    print(f"File meta err: {e}")
            elif isinstance(message, bytes):
                self.file_buffers[current_id].extend(message)
                meta = self.file_metadata[current_id]
                if meta and meta.get("size"):
                    progress = len(self.file_buffers[current_id]) / meta["size"]
                    self.update_ui_cb("file_progress", member_id=current_id, progress=progress)

    def send_chat(self, msg):
        payload_bytes = json.dumps({"type": "chat", "msg": msg}).encode('utf-8')
        # 必须跨线程安全地在 asyncio 循环中调用底层网络库
        def _send_sync():
            try:
                for remote_id, channel in self.channels.items():
                    print(f"[WebRTC] Channel {remote_id} state is {channel.readyState}")
                    if channel.readyState == "open":
                        channel.send(payload_bytes)
                        print(f"[WebRTC Thread] Sent to {remote_id}")
            except Exception as e:
                print(f"[WebRTC Thread] Send Error: {e}")
        self.loop.call_soon_threadsafe(_send_sync)

    def send_file(self, filepath):
        import os
        filename = os.path.basename(filepath)
        size = os.path.getsize(filepath)
        
        def _send():
            meta = json.dumps({"type": "file_meta", "name": filename, "size": size})
            for ch in self.file_channels.values():
                if ch.readyState == "open":
                    ch.send(meta)
                    
            async def _pump():
                with open(filepath, "rb") as f:
                    sent_bytes = 0
                    while chunk := f.read(16384):
                        for ch in self.file_channels.values():
                            if ch.readyState == "open":
                                # Dynamic Flow Control: Backpressure loop (wait if buffer > 1MB)
                                while getattr(ch, "bufferedAmount", 0) > 1024 * 1024:
                                    await asyncio.sleep(0.01)
                                ch.send(chunk)
                        
                        sent_bytes += len(chunk)
                        self.update_ui_cb("file_progress", member_id="local", progress=sent_bytes/size)
                        await asyncio.sleep(0)  # Yield control without artificial delay
                
                done_msg = json.dumps({"type": "file_done"})
                for ch in self.file_channels.values():
                    if ch.readyState == "open":
                        ch.send(done_msg)
            self.loop.create_task(_pump())
        self.loop.call_soon_threadsafe(_send)

    def _setup_peer_connection(self, pc, remote_id):
        # 使用固定 ID 强制建立通信通道，绕过 aiortc 动态握手丢包的 BUG
        channel = pc.createDataChannel("chat", negotiated=True, id=1)
        self._setup_datachannel(channel, remote_id)
        
        file_channel = pc.createDataChannel("file", negotiated=True, id=2)
        self._setup_filechannel(file_channel, remote_id)
        
        pc.addTrack(self.local_mic)
        
        @pc.on("track")
        def on_track(track):
            if track.kind == "audio":
                def on_level(rms):
                    self.update_ui_cb("talking", member_id=remote_id, rms=rms)
                start_playback_loop(track, self.playback_mgr, on_level)
                
        @pc.on("connectionstatechange")
        async def on_connectionstatechange():
            if pc.connectionState == "connected":
                self.update_ui_cb("status", member_id=remote_id, status="connected")
                if remote_id not in self.poll_tasks:
                    self.poll_tasks[remote_id] = asyncio.create_task(self.monitor_stats(pc, remote_id))

    async def host_accept_offer(self, offer_b64, local_id, callback):
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
            
            # Switch internal keys from 'host' placeholder to real remote_id
            pc = self.connections.pop('host')
            self.connections[remote_id] = pc
            if 'host' in self.channels:
                chan = self.channels.pop('host')
                self.channels[remote_id] = chan
                
            if 'host' in self.file_channels:
                f_chan = self.file_channels.pop('host')
                self.file_channels[remote_id] = f_chan
                
                f_buf = self.file_buffers.pop('host')
                self.file_buffers[remote_id] = f_buf
                
                f_meta = self.file_metadata.pop('host')
                self.file_metadata[remote_id] = f_meta
            
            if 'host' in self.poll_tasks:
                task = self.poll_tasks.pop('host')
                self.poll_tasks[remote_id] = task

            callback(remote_id, False)
        except Exception as e:
            callback(str(e), True)

    def shutdown(self):
        for task in self.poll_tasks.values():
            task.cancel()
        for pc in self.connections.values():
            asyncio.run_coroutine_threadsafe(pc.close(), self.loop)

    def reset(self):
        self.shutdown()
        self.connections.clear()
        self.channels.clear()
        self.poll_tasks.clear()
        self.file_channels.clear()
        self.file_buffers.clear()
        self.file_metadata.clear()
