import json
import asyncio
from core.engine import WebRTCEngine
from utils.events import event_bus

class CoreAPI:
    """
    Facade for the underlying WebRTC Engine. 
    Exposes explicit methods for upper layers to interact with the network,
    hiding the internal complexities of WebRTC and Crypto.
    """
    def __init__(self, loop, db, crypto):
        self.db = db
        self._engine = WebRTCEngine(loop)
        self.crypto = crypto
        self.local_id = self.crypto.get_public_key()
        self._engine.local_id = self.local_id
        
        self.callsign = "Unknown"
        self._engine.callsign = self.callsign
        self.callsign_map = self.db.get_all_contacts()
        self.callsign_map[self.local_id] = self.callsign
        
        self.message_handlers = []
        
        from core.topology import TopologyManager
        self.topology = TopologyManager(self._engine, self)
        self.topology.start()
        
        # Register hooks with Engine
        from core.router import MessageRouter
        self.router = MessageRouter(self)
        self._engine.on_channel_open_callbacks.append(self.router.handle_channel_open)
        self._engine.on_channel_message_callbacks.append(self.router.handle_message)
        
        from core.migration_coordinator import MigrationCoordinator
        self.migration_coordinator = MigrationCoordinator(self)
        
    def set_callsign(self, callsign):
        self.callsign = callsign
        self._engine.callsign = callsign
        self.callsign_map[self.local_id] = callsign

    # --- Identity & State ---
    def get_local_id(self):
        return self.local_id
        
    def get_callsign(self):
        return self.callsign
        
    def get_connections(self):
        return list(self._engine.connections.keys())
        
    def get_event_loop(self):
        return self._engine.loop

    def get_data_channel(self, peer_id, label):
        if peer_id in self._engine.data_channels:
            return self._engine.data_channels[peer_id].get(label)
        return None
        
    def get_all_data_channels(self, label):
        channels = {}
        for rid, chans in self._engine.data_channels.items():
            ch = chans.get(label)
            if ch: channels[rid] = ch
        return channels

    # --- Actions ---
    def send_on_channel(self, peer_id, label, data):
        data["sender"] = self.local_id
        data["callsign"] = self.callsign
        signed_data = self.crypto.sign_payload(data)
        
        # [E2EE Wrapper]
        if label in ["chat", "file"] and self.crypto.room_key:
            import base64
            signed_data = {
                "sender": self.local_id,
                "e2ee_payload": base64.b64encode(self.crypto.encrypt_payload(json.dumps(signed_data).encode('utf-8'))).decode('utf-8')
            }
            
        payload_bytes = json.dumps(signed_data).encode('utf-8')
        if peer_id in self._engine.data_channels:
            ch = self._engine.data_channels[peer_id].get(label)
            if ch and ch.readyState == "open":
                ch.send(payload_bytes)

    def broadcast_on_channel(self, label, data):
        data["sender"] = self.local_id
        data["callsign"] = self.callsign
        signed_data = self.crypto.sign_payload(data)
        
        # [E2EE Wrapper]
        if label in ["chat", "file"] and self.crypto.room_key:
            import base64
            signed_data = {
                "sender": self.local_id,
                "e2ee_payload": base64.b64encode(self.crypto.encrypt_payload(json.dumps(signed_data).encode('utf-8'))).decode('utf-8')
            }
            
        payload_bytes = json.dumps(signed_data).encode('utf-8')
        for rid, channels in self._engine.data_channels.items():
            ch = channels.get(label)
            if ch and ch.readyState == "open":
                ch.send(payload_bytes)

    # Note: governance still uses 'broadcast_message' and 'relay_message'
    def broadcast_message(self, data):
        self.broadcast_on_channel("control", data)
        
    def relay_message(self, data, skip_id):
        payload_bytes = json.dumps(data).encode('utf-8')
        for rid, channels in self._engine.data_channels.items():
            if rid != skip_id:
                ch = channels.get("control")
                if ch and ch.readyState == "open":
                    ch.send(payload_bytes)
                    
    def close_connection(self, peer_id):
        if peer_id in self._engine.connections:
            asyncio.run_coroutine_threadsafe(self._engine.connections[peer_id].close(), self._engine.loop)
            
    def reset_node(self):
        self._engine.reset()
        self.topology.stop()
        
    # --- Manual Signaling Wizards ---
    def host_accept_offer(self, offer_b64, callback):
        from core.signaling_wizard import SignalingWizard
        wizard = SignalingWizard(self._engine)
        return asyncio.run_coroutine_threadsafe(
            wizard.host_accept_offer(offer_b64, callback), 
            self._engine.loop
        )
        
    def client_generate_offer(self, callback):
        from core.signaling_wizard import SignalingWizard
        wizard = SignalingWizard(self._engine)
        return asyncio.run_coroutine_threadsafe(
            wizard.client_generate_offer(callback),
            self._engine.loop
        )
        
    def client_accept_answer(self, ans_b64, callback):
        from core.signaling_wizard import SignalingWizard
        wizard = SignalingWizard(self._engine)
        return asyncio.run_coroutine_threadsafe(
            wizard.client_accept_answer(ans_b64, callback),
            self._engine.loop
        )

    # --- Media / Tracks ---
    def add_local_track(self, track):
        """Allows services to register a media track (audio/video) before connections form."""
        self._engine.local_tracks.append(track)
        
    def register_track_handler(self, callback):
        """callback(peer_id, track)"""
        self._engine.on_track_received_callbacks.append(callback)

    # --- Hook Registrations ---
    def set_auth_hook(self, func):
        self._engine.auth_hook = func
        
    def set_meta_hook(self, func):
        self._engine.meta_hook = func
        
    def register_disconnect_handler(self, callback):
        self._engine.on_peer_disconnected_callbacks.append(callback)
        
    def register_message_handler(self, callback):
        self.message_handlers.append(callback)


