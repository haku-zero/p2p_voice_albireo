import json
import uuid
from utils.events import event_bus

class ChatManager:
    def __init__(self, engine):
        self.engine = engine
        event_bus.on("network_message_received", self.handle_network_message)

    def handle_network_message(self, data, current_id):
        if data.get("type") != "chat":
            return
            
        msg_id = data.get("msg_id")
        if msg_id and msg_id in self.engine.chat_seen:
            return
        if msg_id:
            self.engine.chat_seen.add(msg_id)
            
        sender = data.get("sender", current_id)
        csign = self.engine.callsign_map.get(sender, sender[:8])
        event_bus.emit("chat_message", csign, data["msg"])
        
        # Gossip relay
        payload_bytes = json.dumps(data).encode('utf-8')
        for rid, ch in self.engine.channels.items():
            if rid != current_id and ch.readyState == "open":
                ch.send(payload_bytes)

    def send_chat(self, msg):
        msg_id = str(uuid.uuid4())
        self.engine.chat_seen.add(msg_id)
        payload = {
            "type": "chat", 
            "msg_id": msg_id, 
            "sender": getattr(self.engine, "local_id", "Unknown"), 
            "callsign": getattr(self.engine, "callsign", "Unknown"), 
            "msg": msg
        }
        payload = self.engine.crypto.sign_payload(payload)
        payload_bytes = json.dumps(payload).encode('utf-8')
        
        def _send_sync():
            try:
                for remote_id, channel in self.engine.channels.items():
                    if channel.readyState == "open":
                        channel.send(payload_bytes)
            except Exception as e:
                print(f"[ChatManager] Send Error: {e}")
                
        self.engine.loop.call_soon_threadsafe(_send_sync)
