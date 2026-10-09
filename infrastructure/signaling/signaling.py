import json
import base64
import zlib

class SignalingCodec:
    """
    Handles encoding, decoding, and compressing of manual WebRTC 
    signaling payloads and internal mesh routing messages.
    """
    @staticmethod
    def encode_offer(sdp, sdp_type, local_id, callsign):
        sdp_dict = {"sdp": sdp, "type": sdp_type, "user_id": local_id, "callsign": callsign}
        offer_bytes = json.dumps(sdp_dict).encode('utf-8')
        return base64.b64encode(zlib.compress(offer_bytes)).decode()
        
    @staticmethod
    def decode_payload(payload_b64, default_user_id="Unknown"):
        try:
            raw_bytes = base64.b64decode(payload_b64.strip())
            try:
                dec_bytes = zlib.decompress(raw_bytes)
            except zlib.error:
                dec_bytes = raw_bytes
            sdp_dict = json.loads(dec_bytes.decode('utf-8'))
            return sdp_dict.get("sdp"), sdp_dict.get("type"), sdp_dict.get("user_id", default_user_id)
        except Exception as e:
            raise ValueError(f"Failed to decode signaling payload: {e}")
            
    @staticmethod
    def build_mesh_signaling_msg(target_id, sender_id, sdp, sdp_type):
        return json.dumps({
            "type": "signaling",
            "target": target_id,
            "sender": sender_id,
            "sdp": sdp,
            "sdp_type": sdp_type
        })
