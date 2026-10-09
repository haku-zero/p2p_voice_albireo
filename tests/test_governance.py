import unittest
import asyncio
from governance.api import GovernanceAPI

class MockCoreAPI:
    def __init__(self):
        self.handlers = []
        self.sent = []
        self.local_id = "user1"
        self.callsign_map = {"user1": "A", "user2": "B"}
        self.loop = asyncio.new_event_loop()
        
    def get_event_loop(self):
        return self.loop
        
    def register_message_handler(self, handler):
        self.handlers.append(handler)
        
    def get_local_id(self):
        return self.local_id
        
    def get_connections(self):
        return ["user2"]
        
    def broadcast_message(self, data):
        self.sent.append(data)
        
    def relay_message(self, data, skip_id):
        pass
        
    def set_auth_hook(self, hook):
        pass
        
    def set_meta_hook(self, hook):
        pass
        
    def register_disconnect_handler(self, handler):
        pass

class TestGovernance(unittest.TestCase):
    def test_governance_voting(self):
        api = MockCoreAPI()
        gov = GovernanceAPI(api)
        
        gov.issue_vote_kick("user2")
        
        self.assertTrue(len(api.sent) > 0)
        msg = api.sent[-1]
        self.assertEqual(msg["type"], "vote_kick_start")
        self.assertEqual(msg["target"], "user2")
        
        vote_id = msg["vote_id"]
        
        gov.cast_vote("user2", vote_id, "yes")
        
        msg = api.sent[-1]
        self.assertEqual(msg["type"], "vote_cast")
        self.assertEqual(msg["choice"], "yes")
