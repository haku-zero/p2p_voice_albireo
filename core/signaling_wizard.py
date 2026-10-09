from core.peer import PeerConnection
from infrastructure.signaling.signaling import SignalingCodec

class SignalingWizard:
    """
    Handles manual out-of-band WebRTC signaling flows (SDP exchange).
    Decoupled from WebRTCEngine to maintain SRP.
    """
    def __init__(self, engine):
        self.engine = engine

    async def host_accept_offer(self, offer_b64, callback):
        self.engine.is_host = True
        try:
            sdp, sdp_type, remote_id = SignalingCodec.decode_payload(offer_b64)
            
            peer = PeerConnection(remote_id, self.engine.loop, self.engine)
            self.engine.connections[remote_id] = peer
            desc = await peer.create_answer(sdp, sdp_type)
            
            ans_b64 = SignalingCodec.encode_offer(desc.sdp, desc.type, self.engine.local_id, self.engine.callsign)
            callback(ans_b64, remote_id, False)
        except Exception as e:
            callback(str(e), None, True)

    async def client_generate_offer(self, callback):
        try:
            peer = PeerConnection('host', self.engine.loop, self.engine)
            self.engine.connections['host'] = peer
            desc = await peer.create_offer()
            
            offer_b64 = SignalingCodec.encode_offer(desc.sdp, desc.type, self.engine.local_id, self.engine.callsign)
            callback(offer_b64, False)
        except Exception as e:
            callback(str(e), True)

    async def client_accept_answer(self, ans_b64, callback):
        try:
            sdp, sdp_type, remote_id = SignalingCodec.decode_payload(ans_b64, "Host")
            
            if 'host' in self.engine.connections:
                peer = self.engine.connections.pop('host')
                await peer.set_remote_description(sdp, sdp_type)
                peer.peer_id = remote_id
                self.engine.connections[remote_id] = peer
                
            if 'host' in self.engine.data_channels:
                self.engine.data_channels[remote_id] = self.engine.data_channels.pop('host')
                
            callback(remote_id, False)
        except Exception as e:
            callback(str(e), True)
