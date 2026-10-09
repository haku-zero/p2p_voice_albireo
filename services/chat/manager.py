import json
import uuid
import time
from utils.events import event_bus

class ChatManager:
    def __init__(self, core_api, db):
        self.core_api = core_api
        self.db = db
        self.chat_seen = set()
        self.core_api.register_message_handler(self.handle_network_message)

    def has_seen_msg(self, msg_id):
        return msg_id in self.chat_seen
        
    def mark_msg_seen(self, msg_id):
        self.chat_seen.add(msg_id)

    def load_history(self):
        history = self.db.get_all_chats()
        for msg in history:
            s_key = msg["sender_key"]
            csign = self.core_api.callsign_map.get(s_key, s_key[:8])
            self.mark_msg_seen(msg["msg_id"])
            event_bus.emit("chat_message", csign, msg["content"])

    def request_sync(self, target_peer):
        payload = {"type": "chat_sync_req"}
        self.core_api.send_on_channel(target_peer, "chat", payload)

    def handle_network_message(self, peer_id, label, data):
        msg_type = data.get("type", "chat")
        if label != "chat" and msg_type not in ["chat", "chat_sync_req", "chat_sync_res"]:
            return
            
        if msg_type == "chat":
            msg_id = data.get("msg_id")
            if msg_id and self.has_seen_msg(msg_id):
                return
            if msg_id:
                self.mark_msg_seen(msg_id)
                
            sender = data.get("sender", peer_id)
            csign = data.get("callsign", sender[:8])
            content = data.get("msg", "")
            ts = data.get("timestamp", time.time())
            
            self.db.save_chat(msg_id, sender, ts, content)
            event_bus.emit("chat_message", csign, content)
            
        elif msg_type == "chat_sync_req":
            if getattr(self.core_api._engine, "is_host", False):
                history = self.db.get_all_chats()
                res = {"type": "chat_sync_res", "history": history}
                self.core_api.send_on_channel(peer_id, "chat", res)
                
        elif msg_type == "chat_sync_res":
            history = data.get("history", [])
            for msg in history:
                mid = msg["msg_id"]
                if not self.has_seen_msg(mid):
                    self.mark_msg_seen(mid)
                    s_key = msg["sender_key"]
                    csign = self.core_api.callsign_map.get(s_key, s_key[:8])
                    self.db.save_chat(mid, s_key, msg["timestamp"], msg["content"])
                    event_bus.emit("chat_message", csign, msg["content"])

    def send_chat(self, msg):
        msg_id = str(uuid.uuid4())
        self.mark_msg_seen(msg_id)
        ts = time.time()
        
        payload = {
            "type": "chat", 
            "msg_id": msg_id, 
            "msg": msg,
            "timestamp": ts
        }
        
        self.db.save_chat(msg_id, self.core_api.local_id, ts, msg)
        
        def _send_sync():
            try:
                self.core_api.broadcast_on_channel("chat", payload)
            except Exception as e:
                print(f"[ChatManager] Send Error: {e}")
                
        self.core_api.get_event_loop().call_soon_threadsafe(_send_sync)
