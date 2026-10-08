import os
import json
import uuid
import asyncio
from utils import config
from utils.events import event_bus

class FileTransferManager:
    def __init__(self, engine):
        self.engine = engine
        self.file_channels = {}
        self.file_buffers = {}
        self.file_metadata = {}
        self.file_acks = {}
        self.transfer_tasks = []

    def setup_channel(self, channel, initial_id):
        self.file_channels[initial_id] = channel
        
        @channel.on("message")
        def on_message(message):
            current_id = next((rid for rid, ch in self.file_channels.items() if ch == channel), initial_id)
            if isinstance(message, str):
                try:
                    meta = json.loads(message)
                    if meta.get("type") == "file_meta":
                        file_id = meta["file_id"]
                        self.file_metadata[file_id] = meta
                        
                        save_dir = config.load_config().get("save_dir", os.path.join(os.getcwd(), "downloads"))
                        os.makedirs(save_dir, exist_ok=True)
                        f_path = os.path.join(save_dir, meta["name"] + ".part")
                        
                        offset = 0
                        if os.path.exists(f_path):
                            offset = os.path.getsize(f_path)
                            if offset > meta["size"]:
                                offset = 0
                                os.remove(f_path)
                                
                        self.file_buffers[file_id] = {"file": open(f_path, "ab"), "path": f_path, "bytes_received": offset}
                        
                        ack = json.dumps({"type": "file_ack", "file_id": file_id, "offset": offset, "sender": meta.get("sender", "")})
                        channel.send(ack)
                        
                        sender = meta.get("sender", current_id)
                        event_bus.emit("file_incoming", sender, meta["name"], meta["size"], file_id)
                                
                    elif meta.get("type") == "file_ack":
                        file_id = meta.get("file_id")
                        if file_id not in self.file_acks:
                            self.file_acks[file_id] = {}
                        
                        ack_sender = meta.get("sender", current_id)
                        self.file_acks[file_id][ack_sender] = meta.get("offset", 0)
                                    
                    elif meta.get("type") == "file_done":
                        file_id = meta.get("file_id")
                        if file_id in self.file_buffers and file_id in self.file_metadata:
                            f_meta = self.file_metadata[file_id]
                            buf_info = self.file_buffers[file_id]
                            
                            if not buf_info["file"].closed:
                                buf_info["file"].close()
                            
                            save_dir = config.load_config().get("save_dir", os.path.join(os.getcwd(), "downloads"))
                            final_path = os.path.join(save_dir, f_meta["name"])
                            
                            if os.path.exists(final_path):
                                os.remove(final_path)
                            os.rename(buf_info["path"], final_path)
                            
                            sender = f_meta.get("sender", current_id)
                            event_bus.emit("file_done", sender, f_meta["name"], final_path, file_id)
                                    
                            del self.file_buffers[file_id]
                            del self.file_metadata[file_id]
                            self.file_acks.pop(file_id, None)
                except Exception as e:
                    print(f"File meta err: {e}")
            elif isinstance(message, bytes):
                if len(message) < 24: return
                file_id_bytes = message[:16]
                offset_bytes = message[16:24]
                chunk = message[24:]
                
                try:
                    file_id = str(uuid.UUID(bytes=file_id_bytes))
                    chunk_offset = int.from_bytes(offset_bytes, byteorder='little')
                except:
                    return
                
                if file_id in self.file_buffers:
                    meta = self.file_metadata[file_id]
                    buf_info = self.file_buffers[file_id]
                    
                    if chunk_offset < buf_info["bytes_received"]:
                        overlap = buf_info["bytes_received"] - chunk_offset
                        if overlap < len(chunk):
                            chunk = chunk[overlap:]
                            buf_info["file"].write(chunk)
                            buf_info["bytes_received"] += len(chunk)
                    elif chunk_offset == buf_info["bytes_received"]:
                        buf_info["file"].write(chunk)
                        buf_info["bytes_received"] += len(chunk)
                    else:
                        buf_info["file"].write(chunk)
                        buf_info["bytes_received"] += len(chunk)
                        
                    if meta and meta.get("size"):
                        progress = buf_info["bytes_received"] / meta["size"]
                        sender = meta.get("sender", current_id)
                        event_bus.emit("file_progress", sender, progress, file_id)

    def send_file(self, filepath, sender_id):
        filename = os.path.basename(filepath)
        size = os.path.getsize(filepath)
        file_id = str(uuid.uuid4())
        file_id_bytes = uuid.UUID(file_id).bytes
        self.file_acks[file_id] = {}
        
        def _send():
            meta = json.dumps({"type": "file_meta", "file_id": file_id, "sender": sender_id, "name": filename, "size": size})
            for ch in self.file_channels.values():
                if ch.readyState == "open":
                    ch.send(meta)
                    
            def _pump_to_channel(ch_id, ch, is_primary):
                async def _inner():
                    # Wait up to 3 seconds for ACK
                    for _ in range(30):
                        if file_id in self.file_acks and ch_id in self.file_acks[file_id]:
                            break
                        await asyncio.sleep(0.1)
                        
                    offset = 0
                    if file_id in self.file_acks and ch_id in self.file_acks[file_id]:
                        offset = self.file_acks[file_id][ch_id]
                        
                    with open(filepath, "rb") as f:
                        if offset > 0:
                            f.seek(offset)
                        sent_bytes = offset
                        
                        while chunk := f.read(16384):
                            offset_bytes = sent_bytes.to_bytes(8, byteorder='little')
                            chunk_with_header = file_id_bytes + offset_bytes + chunk
                            if ch.readyState != "open":
                                break
                            try:
                                while getattr(ch, "bufferedAmount", 0) > 1024 * 1024:
                                    await asyncio.sleep(0.01)
                                ch.send(chunk_with_header)
                            except Exception:
                                break
                            
                            sent_bytes += len(chunk)
                            if is_primary:
                                progress = sent_bytes / size if size > 0 else 1.0
                                event_bus.emit("file_progress", "local", progress, file_id)
                            await asyncio.sleep(0)
                    
                    if ch.readyState == "open":
                        done_msg = json.dumps({"type": "file_done", "file_id": file_id, "sender": sender_id})
                        ch.send(done_msg)
                return _inner()
                
            open_channels = {rid: ch for rid, ch in self.file_channels.items() if ch.readyState == "open"}
            for i, (rid, ch) in enumerate(open_channels.items()):
                t = self.engine.loop.create_task(_pump_to_channel(rid, ch, is_primary=(i == 0)))
                self.transfer_tasks.append(t)
        self.engine.loop.call_soon_threadsafe(_send)
        return file_id

    def rename_connection(self, old_id, new_id):
        if old_id in self.file_channels:
            f_chan = self.file_channels.pop(old_id)
            self.file_channels[new_id] = f_chan

    def remove_connection(self, peer_id):
        if peer_id in self.file_channels:
            del self.file_channels[peer_id]
        
        to_delete = [fid for fid, meta in self.file_metadata.items() if meta and meta.get("sender") == peer_id]
        for fid in to_delete:
            if fid in self.file_buffers:
                if not self.file_buffers[fid]["file"].closed:
                    self.file_buffers[fid]["file"].close()
            self.file_buffers.pop(fid, None)
            self.file_metadata.pop(fid, None)

    def clear(self):
        for t in self.transfer_tasks:
            if not t.done():
                t.cancel()
        self.transfer_tasks.clear()
        
        self.file_channels.clear()
        for buf in self.file_buffers.values():
            if not buf["file"].closed:
                buf["file"].close()
        self.file_buffers.clear()
        self.file_metadata.clear()
        self.file_acks.clear()
