import asyncio
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCConfiguration, RTCIceServer
from utils.config import load_config

class PeerConnection:
    """
    Wraps a single RTCPeerConnection and its lifecycle.
    Manages tracks, datachannels, and events for a single remote peer.
    """
    def __init__(self, peer_id, loop, engine_ref, force_relay=None):
        self.peer_id = peer_id
        self.loop = loop
        self.engine = engine_ref
        
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
                
        # Determine whether to force TURN relay (e.g., behind strict Symmetric NAT)
        if force_relay is None:
            self.force_relay = getattr(self.engine, "force_relay", False) or cfg.get("force_relay", False)
        else:
            self.force_relay = force_relay
            
        if self.force_relay:
            print(f"[PeerConnection:{self.peer_id}] Enforcing TURN Relay-only policy (Symmetric NAT fallback).")
            
        configuration = RTCConfiguration(iceServers=ice_servers)
        self.pc = RTCPeerConnection(configuration)
        
        self.is_closed = False
        self._disconnect_timer = None
        self._is_ghost = False
        
        self._setup_connection()

    def _setup_connection(self):
        # Pre-negotiated datachannels
        for label, cid in self.engine.channel_configs:
            channel = self.pc.createDataChannel(label, negotiated=True, id=cid)
            self._setup_channel_events(channel, label)
            
        # Add local media tracks
        added_tracks = set()
        for track in self.engine.local_tracks:
            if track not in added_tracks:
                try:
                    self.pc.addTrack(track)
                    added_tracks.add(track)
                except Exception as e:
                    print(f"[PeerConnection] Warning adding local track: {e}")
            
        for factory in self.engine.local_track_factories:
            try:
                track = factory(self.peer_id)
                if track and track not in added_tracks:
                    self.pc.addTrack(track)
                    added_tracks.add(track)
            except Exception as e:
                print(f"[PeerConnection] Warning adding factory track: {e}")
            
        # Track reception
        @self.pc.on("track")
        def on_track(track):
            self.engine.dispatch_track(self.peer_id, track)
            
        # Connection state monitoring
        @self.pc.on("connectionstatechange")
        async def on_connectionstatechange():
            state = self.pc.connectionState
            if state == "connected":
                if self._disconnect_timer:
                    self._disconnect_timer.cancel()
                    self._disconnect_timer = None
                if self._is_ghost:
                    self._is_ghost = False
                    self.engine.handle_peer_ghost(self.peer_id, False)
                self.engine.handle_peer_connected(self.peer_id)
            elif state == "disconnected":
                # Network glitch / transient packet loss: enter 15s Ghost Grace Period
                if not self.is_closed and not self._is_ghost:
                    self._is_ghost = True
                    self.engine.handle_peer_ghost(self.peer_id, True)
                    
                    async def _grace_timeout():
                        try:
                            await asyncio.sleep(15.0)
                            if not self.is_closed and self._is_ghost:
                                self.is_closed = True
                                self._disconnect_timer = None
                                self.engine.handle_peer_disconnected(self.peer_id)
                        except asyncio.CancelledError:
                            pass
                            
                    self._disconnect_timer = self.loop.create_task(_grace_timeout())
            elif state in ["closed", "failed"]:
                if state == "failed" and not self.force_relay:
                    print(f"[PeerConnection:{self.peer_id}] ICE connection failed. Symmetric NAT detected. Consider enabling TURN Relay in settings.")
                if self._disconnect_timer:
                    self._disconnect_timer.cancel()
                    self._disconnect_timer = None
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

    def _filter_relay_candidates(self, sdp):
        lines = sdp.split("\r\n")
        has_relay = any(line.startswith("a=candidate:") and " typ relay" in line for line in lines)
        if not has_relay:
            return sdp
        filtered = [line for line in lines if not (line.startswith("a=candidate:") and " typ relay" not in line)]
        return "\r\n".join(filtered)

    async def create_offer(self):
        offer = await self.pc.createOffer()
        await self.pc.setLocalDescription(offer)
        await asyncio.sleep(1.5)  # Let ICE gather
        if self.force_relay and self.pc.localDescription:
            sdp = self._filter_relay_candidates(self.pc.localDescription.sdp)
            return RTCSessionDescription(sdp=sdp, type=self.pc.localDescription.type)
        return self.pc.localDescription

    async def create_answer(self, remote_sdp, sdp_type):
        desc = RTCSessionDescription(sdp=remote_sdp, type=sdp_type)
        await self.pc.setRemoteDescription(desc)
        answer = await self.pc.createAnswer()
        await self.pc.setLocalDescription(answer)
        await asyncio.sleep(1.5)
        if self.force_relay and self.pc.localDescription:
            sdp = self._filter_relay_candidates(self.pc.localDescription.sdp)
            return RTCSessionDescription(sdp=sdp, type=self.pc.localDescription.type)
        return self.pc.localDescription

    async def set_remote_description(self, remote_sdp, sdp_type):
        desc = RTCSessionDescription(sdp=remote_sdp, type=sdp_type)
        await self.pc.setRemoteDescription(desc)

    async def close(self):
        if self._disconnect_timer:
            self._disconnect_timer.cancel()
            self._disconnect_timer = None
        self.is_closed = True
        if self.pc.connectionState != "closed":
            await self.pc.close()
