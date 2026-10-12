import unittest
import json
from infrastructure.signaling.signaling import SignalingCodec

class TestSignaling(unittest.TestCase):
    def test_signaling_encode_decode(self):
        sdp = "v=0\r\no=- 0 0 IN IP4 127.0.0.1\r\ns=-\r\n"
        sdp_type = "offer"
        local_id = "user1234"
        callsign = "Maverick"
        
        encoded = SignalingCodec.encode_offer(sdp, sdp_type, local_id, callsign)
        self.assertIsInstance(encoded, str)
        self.assertTrue(len(encoded) > 0)
        
        dec_sdp, dec_type, dec_user = SignalingCodec.decode_payload(encoded)
        self.assertEqual(dec_sdp, sdp)
        self.assertEqual(dec_type, sdp_type)
        self.assertEqual(dec_user, local_id)

    def test_mesh_signaling_msg(self):
        msg_str = SignalingCodec.build_mesh_signaling_msg("target", "sender", "sdp_content", "offer")
        msg_dict = json.loads(msg_str)
        self.assertEqual(msg_dict["type"], "signaling")
        self.assertEqual(msg_dict["target"], "target")
        self.assertEqual(msg_dict["sender"], "sender")
        self.assertEqual(msg_dict["sdp"], "sdp_content")
        self.assertEqual(msg_dict["sdp_type"], "offer")

    def test_dtls_fingerprint_binding(self):
        from infrastructure.crypto import CryptoManager
        crypto = CryptoManager()
        sdp = (
            "v=0\r\n"
            "o=- 0 0 IN IP4 127.0.0.1\r\n"
            "s=-\r\n"
            "a=fingerprint:sha-256 11:22:33:44:55:66:77:88:99:AA:BB:CC:DD:EE:FF:00:11:22:33:44:55:66:77:88:99:AA:BB:CC:DD:EE:FF:00\r\n"
        )
        encoded = SignalingCodec.encode_offer(sdp, "offer", crypto.get_public_key(), "Goose", crypto_mgr=crypto)
        
        # Successful decode and verification
        dec_sdp, dec_type, dec_user = SignalingCodec.decode_payload(encoded, crypto_mgr=crypto)
        self.assertEqual(dec_sdp, sdp)
        self.assertEqual(dec_type, "offer")
        self.assertEqual(dec_user, crypto.get_public_key())

    def test_dtls_fingerprint_mismatch_mitm_rejection(self):
        from infrastructure.crypto import CryptoManager
        crypto = CryptoManager()
        valid_fp = "sha-256 11:22:33:44:55:66:77:88:99:AA:BB:CC:DD:EE:FF:00:11:22:33:44:55:66:77:88:99:AA:BB:CC:DD:EE:FF:00"
        sdp = f"v=0\r\na=fingerprint:{valid_fp}\r\n"
        encoded = SignalingCodec.encode_offer(sdp, "offer", crypto.get_public_key(), "Goose", crypto_mgr=crypto)
        
        # Simulate MITM attacker tampering with SDP in base64 payload to point to attacker's DTLS cert
        import zlib, base64
        raw = zlib.decompress(base64.b64decode(encoded))
        d = json.loads(raw.decode())
        # Replace SDP fingerprint with attacker's cert while keeping claimed fingerprint
        d["sdp"] = "v=0\r\na=fingerprint:sha-256 FF:FF:FF:FF:FF:FF:FF:FF:FF:FF:FF:FF:FF:FF:FF:FF:FF:FF:FF:FF:FF:FF:FF:FF:FF:FF:FF:FF:FF:FF:FF:FF\r\n"
        tampered_bytes = json.dumps(d).encode()
        tampered_b64 = base64.b64encode(zlib.compress(tampered_bytes)).decode()
        
        with self.assertRaises(ValueError):
            SignalingCodec.decode_payload(tampered_b64, crypto_mgr=crypto)
