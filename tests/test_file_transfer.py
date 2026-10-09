import unittest
import os
import asyncio
from services.file_transfer.manager import FileTransferManager

class MockCoreAPI:
    def __init__(self):
        self.handlers = []
        self.sent = []
        self.loop = asyncio.new_event_loop()
        
    def register_message_handler(self, handler):
        self.handlers.append(handler)
        
    def get_event_loop(self):
        return self.loop
        
    def broadcast_on_channel(self, label, data):
        self.sent.append(data)
        
    def get_all_data_channels(self, label):
        return {}

class MockCrypto:
    room_key = None

class TestFileTransfer(unittest.TestCase):
    def test_file_transfer_init(self):
        api = MockCoreAPI()
        crypto = MockCrypto()
        mgr = FileTransferManager(api, crypto)
        
        test_file = "test_dummy.txt"
        with open(test_file, "w") as f:
            f.write("hello")
            
        fid = mgr.send_file(test_file, "local")
        
        api.loop.call_soon(api.loop.stop)
        api.loop.run_forever()
        
        self.assertEqual(len(api.sent), 1)
        self.assertEqual(api.sent[0]["type"], "file_meta")
        self.assertEqual(api.sent[0]["name"], "test_dummy.txt")
        
        os.remove(test_file)
