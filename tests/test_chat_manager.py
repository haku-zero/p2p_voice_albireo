import unittest
import asyncio
from services.chat.manager import ChatManager
from utils.events import event_bus

class MockCoreAPI:
    def __init__(self):
        self.handlers = []
        self.sent = []
        self.local_id = "local_peer"
        self.callsign_map = {"peer1": "test"}
        self.loop = asyncio.new_event_loop()
        
    def register_message_handler(self, handler):
        self.handlers.append(handler)
        
    def get_event_loop(self):
        return self.loop
        
    def broadcast_on_channel(self, label, payload):
        self.sent.append((label, payload))

class MockDB:
    def __init__(self):
        self.chats = []
    def save_chat(self, msg_id, sender, ts, content):
        self.chats.append((msg_id, sender, content))
    def get_all_chats(self):
        return []

class TestChatManager(unittest.TestCase):
    def test_chat_send_receive(self):
        api = MockCoreAPI()
        db = MockDB()
        mgr = ChatManager(api, db)
        
        mgr.send_chat("Hello world")
        
        api.loop.call_soon(api.loop.stop)
        api.loop.run_forever()
        
        self.assertEqual(len(api.sent), 1)
        self.assertEqual(api.sent[0][0], "chat")
        self.assertEqual(api.sent[0][1]["msg"], "Hello world")
        
        emitted = []
        def on_chat(c, m):
            emitted.append((c, m))
        event_bus.on("chat_message", on_chat)
        
        payload = {"type": "chat", "msg": "Hi back", "msg_id": "123", "sender": "peer1", "callsign": "test"}
        for h in api.handlers:
            h("peer1", "chat", payload)
            
        self.assertEqual(len(emitted), 1)
        self.assertEqual(emitted[0][0], "test")
        self.assertEqual(emitted[0][1], "Hi back")
        
        self.assertTrue(mgr.has_seen_msg("123"))
        
        event_bus.off("chat_message", on_chat)
