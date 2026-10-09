import os
import json
import uuid
import asyncio
from utils import config
from utils.events import event_bus

class FileTransferManager:
    def __init__(self, core_api, crypto):
        self.core_api = core_api
        self.crypto = crypto
        self.file_buffers = {}
        self.file_metadata = {}
        self.file_acks = {}
        self.transfer_tasks = []
        
        self.core_api.register_message_handler(self.handle_network_message)

    def handle_network_message(self, peer_id, label, message):
        if label != "file": return
        current_id = peer_id
        
        if isinstance(message, dict):
            # metadata JSON
            try:
                meta = message
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
                    
                    ack = {"type": "file_ack", "file_id": file_id, "offset": offset, "sender": meta.get("sender", "")}
                    self.core_api.send_on_channel(current_id, "file", ack)
                    
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
            if self.crypto.room_key:
                decrypted = self.crypto.decrypt_payload(message)
                if not decrypted: return # Invalid encrypted chunk
                message = decrypted
                
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
            meta = {"type": "file_meta", "file_id": file_id, "sender": sender_id, "name": filename, "size": size}
            self.core_api.broadcast_on_channel("file", meta)
            
            file_channels = self.core_api.get_all_data_channels("file")
            
            def _pump_to_channel(ch_id, ch, is_primary):
                async def _inner():
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
                            
                            if self.crypto.room_key:
                                chunk_with_header = self.crypto.encrypt_payload(chunk_with_header)
                                
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
                        done_msg = {"type": "file_done", "file_id": file_id, "sender": sender_id}
                        self.core_api.send_on_channel(ch_id, "file", done_msg)
                        
                return _inner()
                
            for i, (rid, ch) in enumerate(file_channels.items()):
                t = self.core_api.get_event_loop().create_task(_pump_to_channel(rid, ch, is_primary=(i == 0)))
                self.transfer_tasks.append(t)
                
        self.core_api.get_event_loop().call_soon_threadsafe(_send)
        return file_id

    def remove_connection(self, peer_id):
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
        
        for buf in self.file_buffers.values():
            if not buf["file"].closed:
                buf["file"].close()
        self.file_buffers.clear()
        self.file_metadata.clear()
        self.file_acks.clear()
