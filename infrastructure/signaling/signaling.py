import json
import base64
import zlib
import re

class SignalingCodec:
    """
    Handles encoding, decoding, and compressing of manual WebRTC 
    signaling payloads and internal mesh routing messages.
    Supports DTLS certificate fingerprint extraction and cryptographic Ed25519 signing.
    """
    @staticmethod
    def encode_offer(sdp, sdp_type, local_id, callsign, crypto_mgr=None):
        sdp_dict = {
            "sdp": sdp,
            "type": sdp_type,
            "user_id": local_id,
            "callsign": callsign
        }
        
        # Extract DTLS certificate fingerprint if present in SDP
        if sdp:
            fp_match = re.search(r'a=fingerprint:([^\r\n]+)', sdp)
            if fp_match:
                sdp_dict["fingerprint"] = fp_match.group(1).strip()
                
        # If crypto_mgr provided and enabled, bind with Ed25519 signature
        if crypto_mgr and getattr(crypto_mgr, "enabled", False):
            sdp_dict["pub_key"] = crypto_mgr.get_public_key()
            sdp_dict = crypto_mgr.sign_payload(sdp_dict)
            
        offer_bytes = json.dumps(sdp_dict).encode('utf-8')
        return base64.b64encode(zlib.compress(offer_bytes)).decode()
        
    @staticmethod
    def decode_payload(payload_b64, default_user_id="Unknown", crypto_mgr=None, verify_fingerprint=True):
        try:
            raw_bytes = base64.b64decode(payload_b64.strip())
            try:
                dec_bytes = zlib.decompress(raw_bytes)
            except zlib.error:
                dec_bytes = raw_bytes
            sdp_dict = json.loads(dec_bytes.decode('utf-8'))
            
            sdp = sdp_dict.get("sdp")
            sdp_type = sdp_dict.get("type")
            user_id = sdp_dict.get("user_id", default_user_id)
            
            # Check Ed25519 signature & DTLS fingerprint if present
            signature = sdp_dict.get("signature")
            pub_key = sdp_dict.get("pub_key")
            claimed_fp = sdp_dict.get("fingerprint")
            
            if signature and pub_key:
                is_valid = False
                if crypto_mgr and getattr(crypto_mgr, "enabled", False):
                    is_valid = crypto_mgr.verify_payload(sdp_dict, pub_key)
                else:
                    try:
                        from nacl.signing import VerifyKey
                        from nacl.encoding import HexEncoder
                        sign_dict = {k: v for k, v in sdp_dict.items() if k != 'signature'}
                        serialized = json.dumps(sign_dict, separators=(',', ':'), sort_keys=True).encode('utf-8')
                        verify_key = VerifyKey(pub_key, encoder=HexEncoder)
                        verify_key.verify(serialized, base64.b64decode(signature))
                        is_valid = True
                    except Exception as ex:
                        print(f"[Crypto] DTLS Binding standalone verification failed: {ex}")
                        is_valid = False
                
                if not is_valid:
                    raise ValueError("Cryptographic verification failed: Tampered signaling payload or invalid signature!")
                    
                # Validate DTLS fingerprint matches actual SDP
                if verify_fingerprint and sdp and claimed_fp:
                    fp_match = re.search(r'a=fingerprint:([^\r\n]+)', sdp)
                    if fp_match:
                        actual_fp = fp_match.group(1).strip()
                        if actual_fp != claimed_fp:
                            raise ValueError(
                                f"DTLS Fingerprint mismatch! SDP has '{actual_fp}', but signed payload claims '{claimed_fp}'. MitM attack detected!"
                            )
                    print(f"[Crypto] SDP DTLS Fingerprint verified & bound to peer '{user_id[:8]}...'.")
                    
            return sdp, sdp_type, user_id
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
