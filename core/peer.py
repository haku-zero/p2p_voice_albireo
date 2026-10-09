import asyncio
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCConfiguration, RTCIceServer
from utils.config import load_config

class PeerConnection:
    """
    Wraps a single RTCPeerConnection and its lifecycle.
    Manages tracks, datachannels, and events for a single remote peer.
    """
    def __init__(self, peer_id, loop, engine_ref):
        self.peer_id = peer_id
        self.loop = loop
        
        cfg = load_config()
        ice_servers_config = cfg.get("ice_servers", [
            {"urls": ["stun:stun.l.google.com:19302"]},
            {"urls": ["stun:global.stun.twilio.com:3478"]}
        ])
        
        ice_servers = []
        for s in ice_servers_config:
            if "username" in s and "credential" in s:
                ice_servers.append(RTCIceServer(urls=s["urls"], username=s["username"], credential=s["credential"]))
            else:
                ice_servers.append(RTCIceServer(urls=s["urls"]))
                
        configuration = RTCConfiguration(iceServers=ice_servers)
        self.pc = RTCPeerConnection(configuration)
        
        self.engine = engine_ref
        self.is_closed = False
        
        self._setup_connection()

    def _setup_connection(self):
        # Pre-negotiated datachannels
        for label, cid in self.engine.channel_configs:
            channel = self.pc.createDataChannel(label, negotiated=True, id=cid)
            self._setup_channel_events(channel, label)
            
        # Add local media tracks
        for track in self.engine.local_tracks:
            self.pc.addTrack(track)
            
        for factory in self.engine.local_track_factories:
            self.pc.addTrack(factory(self.peer_id))
            
        # Track reception
        @self.pc.on("track")
        def on_track(track):
            self.engine.dispatch_track(self.peer_id, track)
            
        # Connection state monitoring
        @self.pc.on("connectionstatechange")
        async def on_connectionstatechange():
            state = self.pc.connectionState
            if state == "connected":
                self.engine.handle_peer_connected(self.peer_id)
            elif state in ["closed", "failed", "disconnected"]:
                if not self.is_closed:
                    self.is_closed = True
                    self.engine.handle_peer_disconnected(self.peer_id)

    def _setup_channel_events(self, channel, label):
        self.engine.register_data_channel(self.peer_id, label, channel)
        
        @channel.on("open")
        def on_open():
            self.engine.dispatch_channel_open(self.peer_id, label)
            
        @channel.on("message")
        def on_message(message):
            self.engine.dispatch_channel_message(self.peer_id, label, message)

    async def create_offer(self):
        offer = await self.pc.createOffer()
        await self.pc.setLocalDescription(offer)
        await asyncio.sleep(1.5)  # Let ICE gather
        return self.pc.localDescription

    async def create_answer(self, remote_sdp, sdp_type):
        desc = RTCSessionDescription(sdp=remote_sdp, type=sdp_type)
        await self.pc.setRemoteDescription(desc)
        answer = await self.pc.createAnswer()
        await self.pc.setLocalDescription(answer)
        await asyncio.sleep(1.5)
        return self.pc.localDescription

    async def set_remote_description(self, remote_sdp, sdp_type):
        desc = RTCSessionDescription(sdp=remote_sdp, type=sdp_type)
        await self.pc.setRemoteDescription(desc)

    async def close(self):
        self.is_closed = True
        if self.pc.connectionState != "closed":
            await self.pc.close()
