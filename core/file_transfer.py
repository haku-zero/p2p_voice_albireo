import os
import json
import uuid
import asyncio
from utils import config

class FileTransferManager:
    def __init__(self, engine):
        self.engine = engine
        self.file_channels = {}
        self.file_buffers = {}
        self.file_metadata = {}

    def setup_channel(self, channel, initial_id):
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
                        file_id = meta["file_id"]
                        self.file_metadata[file_id] = meta
                        self.file_buffers[file_id] = bytearray()
                        sender = meta.get("sender", current_id)
                        self.engine.update_ui_cb("file_incoming", member_id=sender, filename=meta["name"], size=meta["size"], file_id=file_id)
                        
                        if self.engine.is_host:
                            for rid, ch in self.file_channels.items():
                                if rid != current_id and ch.readyState == "open":
                                    ch.send(message)
                                
                    elif meta.get("type") == "file_done":
                        file_id = meta.get("file_id")
                        if file_id in self.file_buffers and file_id in self.file_metadata:
                            save_dir = config.load_config().get("save_dir", os.path.join(os.getcwd(), "downloads"))
                            if not os.path.exists(save_dir):
                                os.makedirs(save_dir)
                            f_meta = self.file_metadata[file_id]
                            f_path = os.path.join(save_dir, f_meta["name"])
                            with open(f_path, "wb") as f:
                                f.write(self.file_buffers[file_id])
                            sender = f_meta.get("sender", current_id)
                            self.engine.update_ui_cb("file_done", member_id=sender, filename=f_meta["name"], filepath=f_path, file_id=file_id)
                            
                            if self.engine.is_host:
                                for rid, ch in self.file_channels.items():
                                    if rid != current_id and ch.readyState == "open":
                                        ch.send(message)
                                    
                            del self.file_buffers[file_id]
                            del self.file_metadata[file_id]
                except Exception as e:
                    print(f"File meta err: {e}")
            elif isinstance(message, bytes):
                if len(message) < 16: return
                file_id_bytes = message[:16]
                chunk = message[16:]
                try:
                    file_id = str(uuid.UUID(bytes=file_id_bytes))
                except:
                    return
                
                if file_id in self.file_buffers:
                    self.file_buffers[file_id].extend(chunk)
                    meta = self.file_metadata[file_id]
                    if meta and meta.get("size"):
                        progress = len(self.file_buffers[file_id]) / meta["size"]
                        sender = meta.get("sender", current_id)
                        self.engine.update_ui_cb("file_progress", member_id=sender, progress=progress, file_id=file_id)
                    
                    if self.engine.is_host:
                        for rid, ch in self.file_channels.items():
                            if rid != current_id and ch.readyState == "open":
                                ch.send(message)

    def send_file(self, filepath, sender_id):
        filename = os.path.basename(filepath)
        size = os.path.getsize(filepath)
        file_id = str(uuid.uuid4())
        file_id_bytes = uuid.UUID(file_id).bytes
        
        def _send():
            meta = json.dumps({"type": "file_meta", "file_id": file_id, "sender": sender_id, "name": filename, "size": size})
            for ch in self.file_channels.values():
                if ch.readyState == "open":
                    ch.send(meta)
                    
            async def _pump():
                with open(filepath, "rb") as f:
                    sent_bytes = 0
                    while chunk := f.read(16384):
                        chunk_with_header = file_id_bytes + chunk
                        for ch in list(self.file_channels.values()):
                            if ch.readyState == "open":
                                try:
                                    while getattr(ch, "bufferedAmount", 0) > 1024 * 1024:
                                        await asyncio.sleep(0.01)
                                    ch.send(chunk_with_header)
                                except Exception:
                                    pass
                        
                        sent_bytes += len(chunk)
                        self.engine.update_ui_cb("file_progress", member_id="local", progress=sent_bytes/size, file_id=file_id)
                        await asyncio.sleep(0)
                
                done_msg = json.dumps({"type": "file_done", "file_id": file_id, "sender": sender_id})
                for ch in self.file_channels.values():
                    if ch.readyState == "open":
                        ch.send(done_msg)
            self.engine.loop.create_task(_pump())
        self.engine.loop.call_soon_threadsafe(_send)
        return file_id

    def rename_connection(self, old_id, new_id):
        if old_id in self.file_channels:
            f_chan = self.file_channels.pop(old_id)
            self.file_channels[new_id] = f_chan

    def clear(self):
        self.file_channels.clear()
        self.file_buffers.clear()
        self.file_metadata.clear()
