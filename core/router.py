import json
import asyncio
from utils.events import event_bus

class MessageRouter:
    """
    Handles internal data channel events and message routing.
    Decoupled from CoreAPI to improve cohesion.
    """
    def __init__(self, core_api):
        self.api = core_api

    def handle_channel_open(self, peer_id, label):
        if label == "control":
            if getattr(self.api._engine, "meta_hook", None):
                meta = self.api._engine.meta_hook()
                if meta:
                    self.api.send_on_channel(peer_id, label, meta)
            # Send presence / callsign announcement
            self.api.send_on_channel(peer_id, "control", {
                "type": "presence",
                "callsign": self.api.callsign,
                "sender": self.api.local_id
            })
                    
        # Expose generic channel open event if upper layers need it
        event_bus.emit("channel_opened", peer_id, label)

    def handle_message(self, peer_id, label, raw_message):
        try:
            is_binary = isinstance(raw_message, bytes)
            data = None
            if not is_binary:
                data = json.loads(raw_message)
            else:
                try:
                    decoded = raw_message.decode('utf-8')
                    data = json.loads(decoded)
                    is_binary = False
                except (UnicodeDecodeError, json.JSONDecodeError):
                    pass

            if not is_binary and data:
                # [E2EE Unwrap]
                if "e2ee_payload" in data:
                    if getattr(self.api, "crypto", None) and self.api.crypto.room_key:
                        import base64
                        dec = self.api.crypto.decrypt_payload(base64.b64decode(data["e2ee_payload"]))
                        if dec:
                            data = json.loads(dec.decode('utf-8'))
                            
                # 1. Crypto Verification
                sender = data.get("sender")
                if sender and not self.api.crypto.verify_payload(data, sender):
                    print(f"[Crypto] Dropped spoofed payload from {sender}")
                    return
                    
                # 2. State Sync
                if "callsign" in data and sender:
                    old_callsign = self.api.callsign_map.get(sender)
                    self.api.callsign_map[sender] = data["callsign"]
                    self.api.db.save_contact(sender, data["callsign"])
                    if old_callsign != data["callsign"]:
                        event_bus.emit("peer_callsign_updated", sender, data["callsign"])
                    
                # 3. Handle Internal Control / Signaling
                if label == "control":
                    msg_type = data.get("type")
                    if msg_type == "peer_joined":
                        joined_id = data.get("peer_id")
                        if joined_id and joined_id != self.api.local_id:
                            csign = data.get("callsign", joined_id[:8])
                            if "callsign" in data:
                                self.api.callsign_map[joined_id] = csign
                            event_bus.emit("status", joined_id, "connected")
                            
                    elif msg_type == "peer_left":
                        left_peer_id = data.get("peer_id") or sender
                        if left_peer_id and left_peer_id != self.api.local_id:
                            event_bus.emit("status", left_peer_id, "disconnected")
                            event_bus.emit("peer_left", left_peer_id)
                            if getattr(self.api._engine, "is_host", False) and left_peer_id in self.api._engine.connections:
                                self.api.close_connection(left_peer_id)
                            
                    elif msg_type == "signaling":
                        target = data.get("target")
                        if target == self.api.local_id or target == "all":
                            sdp = data.get("sdp")
                            sdp_type = data.get("sdp_type")
                            asyncio.run_coroutine_threadsafe(self.api._engine._handle_mesh_signaling(sender, sdp, sdp_type), self.api._engine.loop)
                        elif getattr(self.api._engine, "is_host", False) and target in self.api._engine.data_channels:
                            ch = self.api._engine.data_channels[target].get('control')
                            if ch and ch.readyState == "open":
                                ch.send(raw_message)
                                
                    elif msg_type == "roster":
                        self.api.topology.handle_roster_update(data.get("roster", []))
                    
                    event_bus.emit("network_message_received", data, peer_id)
                    
                # [SFU Relay] If we are the Host, relay the message to all other connected peers
                if getattr(self.api._engine, "is_host", False) and data.get("sender") != self.api.local_id:
                    self.api.relay_message(data, skip_id=peer_id)
                    
                # 4. Dispatch Application channels
                for handler in self.api.message_handlers:
                    handler(peer_id, label, data)
            else:
                # [SFU Relay] Relay binary data (e.g. file chunks) to other peers
                if getattr(self.api._engine, "is_host", False):
                    for rid, channels in self.api._engine.data_channels.items():
                        if rid != peer_id:
                            ch = channels.get(label)
                            if ch and ch.readyState == "open":
                                ch.send(raw_message)
                                
                # Dispatch raw binary
                for handler in self.api.message_handlers:
                    handler(peer_id, label, raw_message)
                    
        except Exception as e:
            print(f"[MessageRouter] Message route error: {e}")
