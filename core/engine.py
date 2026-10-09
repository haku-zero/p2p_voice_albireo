import asyncio
import json
from core.peer import PeerConnection
from infrastructure.signaling.signaling import SignalingCodec

class WebRTCEngine:
    """
    Coordinator for all PeerConnections. 
    Maintains the mesh topology and routes internal WebRTC signaling.
    """
    def __init__(self, loop):
        self.loop = loop
        self.connections = {} # {peer_id: PeerConnection}
        self.room_code = None
        self.core_api_ref = None
        
        self.channel_configs = [("control", 1), ("file", 2), ("chat", 3)]
        self.data_channels = {} # {peer_id: {label: RTCDataChannel}}
        
        # Hooks for CoreAPI
        self.on_channel_open_callbacks = [] 
        self.on_channel_message_callbacks = [] 
        self.on_track_received_callbacks = [] 
        self.on_peer_disconnected_callbacks = []
        self.auth_hook = None 
        self.meta_hook = None
        
        self.local_tracks = []
        self.local_track_factories = []
        self.is_host = False
        self.local_id = "Unknown"
        self.callsign = "Unknown"

    # --- Peer Delegation Callbacks ---
    def register_data_channel(self, peer_id, label, channel):
        if peer_id not in self.data_channels:
            self.data_channels[peer_id] = {}
        self.data_channels[peer_id][label] = channel

    def dispatch_channel_open(self, peer_id, label):
        real_id = peer_id
        if peer_id == 'host' and 'host' not in self.data_channels:
            pass
            
        for cb in self.on_channel_open_callbacks:
            cb(real_id, label)

    def dispatch_channel_message(self, peer_id, label, message):
        if self.auth_hook and not self.auth_hook(peer_id):
            return
        try:
            for cb in self.on_channel_message_callbacks:
                cb(peer_id, label, message)
        except Exception as e:
            print(f"[Engine] Message handling error: {e}")

    def dispatch_track(self, peer_id, track):
        for cb in self.on_track_received_callbacks:
            cb(peer_id, track)

    def handle_peer_connected(self, peer_id):
        if self.is_host:
            msg = json.dumps({"type": "peer_joined", "peer_id": peer_id})
            for rid, channels in self.data_channels.items():
                ch = channels.get('control')
                if rid != peer_id and ch and ch.readyState == "open":
                    ch.send(msg)

    def handle_peer_disconnected(self, peer_id):
        if peer_id in self.data_channels:
            del self.data_channels[peer_id]
        if peer_id in self.connections:
            del self.connections[peer_id]
        for cb in self.on_peer_disconnected_callbacks:
            cb(peer_id)
            
        # [Failover Trigger]
        if not self.is_host and len(self.connections) == 0:
            if self.core_api_ref:
                self.core_api_ref.topology.trigger_migration(peer_id)

    # --- Mesh Topology & Signaling ---
    async def _initiate_mesh(self, peer_id):
        peer = PeerConnection(peer_id, self.loop, self)
        self.connections[peer_id] = peer
        desc = await peer.create_offer()
        
        msg = SignalingCodec.build_mesh_signaling_msg(peer_id, self.local_id, desc.sdp, desc.type)
        for rid, channels in self.data_channels.items():
            ch = channels.get('control')
            if ch and ch.readyState == "open":
                ch.send(msg)

    async def _handle_mesh_signaling(self, sender, sdp, sdp_type):
        if sdp_type == "offer":
            peer = PeerConnection(sender, self.loop, self)
            self.connections[sender] = peer
            desc = await peer.create_answer(sdp, sdp_type)
            
            msg = SignalingCodec.build_mesh_signaling_msg(sender, self.local_id, desc.sdp, desc.type)
            for rid, channels in self.data_channels.items():
                ch = channels.get('control')
                if ch and ch.readyState == "open":
                    ch.send(msg)
                    
        elif sdp_type == "answer":
            if sender in self.connections:
                await self.connections[sender].set_remote_description(sdp, sdp_type)

    # --- Manual Wizards ---


    # --- Lifecycle ---
    def shutdown(self):
        async def _shutdown():
            close_tasks = [peer.close() for peer in self.connections.values()]
            if close_tasks:
                await asyncio.gather(*close_tasks, return_exceptions=True)
            await asyncio.sleep(0.1)
            
        future = asyncio.run_coroutine_threadsafe(_shutdown(), self.loop)
        try:
            future.result(timeout=3)
        except Exception:
            pass

    def reset(self):
        self.shutdown()
        self.connections.clear()
        self.data_channels.clear()
        self.is_host = False
