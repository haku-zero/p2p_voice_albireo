import unittest
import asyncio
import json
from core.api import CoreAPI
from infrastructure.crypto import CryptoManager

class MockDB:
    def get_all_contacts(self):
        return {}
    def save_contact(self, *args):
        pass

class TestCoreAPI(unittest.TestCase):
    def test_api_message_routing(self):
        loop = asyncio.new_event_loop()
        db = MockDB()
        crypto = CryptoManager()
        api = CoreAPI(loop, db, crypto)
        
        dispatched = []
        def mock_handler(peer_id, label, data):
            dispatched.append((peer_id, label, data))
            
        api.register_message_handler(mock_handler)
        
        payload = {"type": "chat", "msg": "test", "sender": api.local_id, "callsign": api.callsign}
        signed = api.crypto.sign_payload(payload)
        raw_message = json.dumps(signed).encode('utf-8')
        
        api.router.handle_message("peer_1", "chat", raw_message)
        
        self.assertEqual(len(dispatched), 1)
        self.assertEqual(dispatched[0][0], "peer_1")
        self.assertEqual(dispatched[0][1], "chat")
        self.assertEqual(dispatched[0][2]["msg"], "test")
        
    def test_api_binary_routing(self):
        loop = asyncio.new_event_loop()
        db = MockDB()
        crypto = CryptoManager()
        api = CoreAPI(loop, db, crypto)
        
        dispatched = []
        def mock_handler(peer_id, label, data):
            dispatched.append((peer_id, label, data))
            
        api.register_message_handler(mock_handler)
        
        binary_data = b"some_raw_file_bytes"
        api.router.handle_message("peer_1", "file", binary_data)
        
        self.assertEqual(len(dispatched), 1)
        self.assertEqual(dispatched[0][0], "peer_1")
        self.assertEqual(dispatched[0][1], "file")
        self.assertEqual(dispatched[0][2], b"some_raw_file_bytes")

    def test_api_spoofed_message(self):
        loop = asyncio.new_event_loop()
        db = MockDB()
        crypto = CryptoManager()
        api = CoreAPI(loop, db, crypto)
        
        dispatched = []
        def mock_handler(peer_id, label, data):
            dispatched.append(data)
            
        api.register_message_handler(mock_handler)
        
        payload = {"type": "chat", "msg": "hacked", "sender": api.local_id, "callsign": api.callsign}
        signed = api.crypto.sign_payload(payload)
        signed["msg"] = "changed_after_signing"
        
        raw_message = json.dumps(signed).encode('utf-8')
        
        api.router.handle_message("peer_1", "chat", raw_message)
        
        self.assertEqual(len(dispatched), 0)
