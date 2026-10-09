import unittest
from infrastructure.crypto import CryptoManager
from nacl.signing import SigningKey
from nacl.encoding import HexEncoder

class TestCrypto(unittest.TestCase):
    def test_key_generation(self):
        mgr = CryptoManager()
        pub_key = mgr.get_public_key()
        self.assertIsNotNone(pub_key)
        self.assertTrue(len(pub_key) > 30)

    def test_signing_and_verification(self):
        mgr1 = CryptoManager()
        mgr2 = CryptoManager()
        pub_key1 = mgr1.get_public_key()
        
        payload = {"type": "chat", "msg": "hello"}
        signed_payload = mgr1.sign_payload(payload)
        
        self.assertIn("signature", signed_payload)
        self.assertTrue(mgr1.verify_payload(signed_payload, pub_key1))
        self.assertTrue(mgr2.verify_payload(signed_payload, pub_key1))

    def test_tampered_payload_verification(self):
        mgr = CryptoManager()
        pub_key = mgr.get_public_key()
        
        payload = {"type": "chat", "msg": "hello"}
        signed_payload = mgr.sign_payload(payload)
        signed_payload["msg"] = "hacked"
        
        self.assertFalse(mgr.verify_payload(signed_payload, pub_key))

    def test_spoofed_identity(self):
        mgr1 = CryptoManager()
        sk2 = SigningKey.generate()
        pub_key2 = sk2.verify_key.encode(encoder=HexEncoder).decode('utf-8')
        
        payload = {"type": "chat", "msg": "hello"}
        signed_payload = mgr1.sign_payload(payload)
        self.assertFalse(mgr1.verify_payload(signed_payload, pub_key2))
