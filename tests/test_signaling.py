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
