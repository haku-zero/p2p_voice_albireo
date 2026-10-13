import unittest
import asyncio
import time
from engine.cli import CliRunner
from utils.events import event_bus

class TestCLI(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        self.runner = CliRunner(room_code=None, callsign="Alice_CLI", loop=self.loop)

    def tearDown(self):
        self.runner.stop()
        self.loop.close()

    def test_cli_initialization(self):
        self.assertEqual(self.runner.core_api.get_callsign(), "Alice_CLI")
        self.assertIsNotNone(self.runner.core_api.get_local_id())
        self.assertFalse(self.runner.is_host)
        self.assertIsNone(self.runner.room_code)

    def test_cli_help_and_status(self):
        help_out = self.runner.execute_command("/help")
        self.assertIn("Available CLI Commands", help_out)
        self.assertIn("/join", help_out)
        self.assertIn("/host", help_out)
        self.assertIn("/say", help_out)
        self.assertIn("/history", help_out)
        self.assertIn("/last", help_out)
        self.assertIn("/sync", help_out)

        status_out = self.runner.execute_command("/status")
        self.assertIn("Node Status", status_out)
        self.assertIn("Alice_CLI", status_out)
        self.assertIn(self.runner.core_api.get_local_id(), status_out)

    def test_cli_nick_command(self):
        res = self.runner.execute_command("/nick Bob_CLI")
        self.assertIn("Bob_CLI", res)
        self.assertEqual(self.runner.core_api.get_callsign(), "Bob_CLI")

    def test_cli_chat_not_in_room(self):
        res = self.runner.execute_command("Hello mesh!")
        self.assertIn("Not in a room", res)

        say_res = self.runner.execute_command("/say Hello mesh!")
        self.assertIn("Not in a room", say_res)

    def test_cli_members_empty(self):
        res = self.runner.execute_command("/members")
        self.assertIn("No peers connected", res)

    def test_cli_host_and_leave(self):
        host_res = self.runner.execute_command("/host ROOM99 archon")
        self.assertIn("ROOM99", host_res)
        self.assertTrue(self.runner.is_host)
        self.assertEqual(self.runner.room_code, "ROOM99")
        self.assertTrue(self.runner.gov_api.state.is_archon)

        # Test status reflects host
        status_out = self.runner.execute_command("/status")
        self.assertIn("Host", status_out)
        self.assertIn("ROOM99", status_out)

        # Test leave
        leave_res = self.runner.execute_command("/leave")
        self.assertIn("Left room", leave_res)
        self.assertIsNone(self.runner.room_code)
        self.assertFalse(self.runner.is_host)

    def test_cli_history_empty_and_populated(self):
        self.runner.db.clear_chat_history()
        hist_empty = self.runner.execute_command("/history")
        self.assertIn("No chat history found", hist_empty)

        # Simulate populating chat history in db
        self.runner.db.save_chat("msg1", "peer_bob", time.time() - 10, "Hello Bob here")
        self.runner.db.save_chat("msg2", self.runner.core_api.local_id, time.time() - 5, "Hi Bob, I am Alice")

        hist_out = self.runner.execute_command("/history")
        self.assertIn("Chat History", hist_out)
        self.assertIn("Hello Bob here", hist_out)
        self.assertIn("(You)", hist_out)
        self.assertIn("Hi Bob, I am Alice", hist_out)

        # Test limit
        hist_limit = self.runner.execute_command("/history 1")
        self.assertIn("Last 1 messages", hist_limit)
        self.assertIn("Hi Bob, I am Alice", hist_limit)

    def test_cli_latest_message_tracking_and_last_command(self):
        self.runner.execute_command("/host ROOM100 archon")
        
        # Test empty latest message
        self.runner.latest_message = None
        last_empty = self.runner.execute_command("/last")
        self.assertIn("No messages received", last_empty)

        # Send local message
        self.runner.execute_command("Local test message")
        self.assertIsNotNone(self.runner.latest_message)
        self.assertEqual(self.runner.latest_message["content"], "Local test message")
        self.assertTrue(self.runner.latest_message["is_self"])

        last_out = self.runner.execute_command("/last")
        self.assertIn("Local test message", last_out)
        self.assertIn("(You)", last_out)

        # Simulate incoming remote message via event bus
        event_bus.emit("chat_message", "Charlie", "Incoming remote alert!")
        self.assertEqual(self.runner.latest_message["sender"], "Charlie")
        self.assertEqual(self.runner.latest_message["content"], "Incoming remote alert!")
        self.assertFalse(self.runner.latest_message["is_self"])

        last_remote = self.runner.execute_command("/last")
        self.assertIn("Charlie", last_remote)
        self.assertIn("Incoming remote alert!", last_remote)

    def test_cli_prompt_generation(self):
        # Empty prompt
        self.runner.latest_message = None
        self.assertEqual(self.runner.get_prompt() if hasattr(self.runner, 'get_prompt') else self.runner._get_prompt(), "albireo> ")

        # Populated prompt
        self.runner._update_latest_message("Dave", "Briefing starts now", timestamp=time.time())
        prompt = self.runner._get_prompt()
        self.assertIn("最新消息", prompt)
        self.assertIn("Dave", prompt)
        self.assertIn("Briefing starts now", prompt)
        self.assertIn("albireo> ", prompt)

    def test_cli_sync_command(self):
        # Sync when not in room
        res = self.runner.execute_command("/sync")
        self.assertIn("Not in a room", res)

        # Sync when host
        self.runner.execute_command("/host SYNCROOM archon")
        res_host = self.runner.execute_command("/sync")
        self.assertIn("You are the Host", res_host)

    def test_cli_clear_history(self):
        self.runner.db.save_chat("msg_temp", "some_peer", time.time(), "Temporary chat")
        self.runner._update_latest_message("some_peer", "Temporary chat")
        self.assertIsNotNone(self.runner.latest_message)

        clear_res = self.runner.execute_command("/clear history")
        self.assertIn("Chat history cleared", clear_res)
        self.assertIsNone(self.runner.latest_message)
        self.assertEqual(len(self.runner.db.get_all_chats()), 0)

    def test_cli_governance_validation(self):
        self.runner.execute_command("/host ROOM88 archon")
        kick_res = self.runner.execute_command("/kick non_existent_peer")
        self.assertIn("not found", kick_res)

        heir_res = self.runner.execute_command("/heir non_existent_peer")
        self.assertIn("not found", heir_res)

        vote_err = self.runner.execute_command("/vote target maybe")
        self.assertIn("Choice must be 'yes' or 'no'", vote_err)

    def test_cli_quit_command(self):
        self.runner.running = True
        quit_res = self.runner.execute_command("/quit")
        self.assertIn("Exiting", quit_res)
        self.assertFalse(self.runner.running)

if __name__ == '__main__':
    unittest.main()
