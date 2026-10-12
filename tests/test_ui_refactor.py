import os
import sys
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import customtkinter as ctk

from ui.theme import DANGER, PRIMARY
from ui.store import store
from ui.top_bar import TopBarView
from ui.member_view import MemberView
from ui.modals import VoteModal, ElectionModal, generate_secure_room_code
from ui.ui_manager import UIManager


class TestUIRefactor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Initialize headless CTk root
        cls.root = ctk.CTk()
        cls.root.withdraw()
        cls.root.local_id = "local_node_test_id_12345"

    @classmethod
    def tearDownClass(cls):
        try:
            cls.root.destroy()
        except Exception:
            pass

    def test_secure_room_code_generation(self):
        code1 = generate_secure_room_code()
        code2 = generate_secure_room_code()
        self.assertNotEqual(code1, code2)
        self.assertEqual(len(code1), 9) # XXXX-XXXX
        self.assertIn("-", code1)

    def test_top_bar_view_lifecycle(self):
        media_ctrl = MagicMock()
        media_ctrl.inputs_map = {"Default Mic": 0}
        media_ctrl.outputs_map = {"Default Speaker": 0}
        media_ctrl.change_mic_mode.return_value = "open_mic"
        
        core_api = MagicMock()
        core_api._engine.is_host = True
        gov_api = MagicMock()
        chat_view = MagicMock()
        exit_mock = MagicMock()

        top_bar = TopBarView(self.root, media_ctrl, core_api, gov_api, chat_view, exit_mock)
        self.assertIsNotNone(top_bar.container)
        self.assertIsNotNone(top_bar.mic_btn)
        self.assertIsNotNone(top_bar.speaker_btn)

        # Test store data-binding to TopBarView
        store.dispatch("TOGGLE_MIC", True)
        self.assertEqual(top_bar.mic_btn.cget("text_color"), DANGER)

        store.dispatch("TOGGLE_MIC", False)
        self.assertEqual(top_bar.mic_btn.cget("text_color"), PRIMARY)

        # Test destroy and unsubscription
        top_bar.destroy()
        self.assertFalse(top_bar._alive)

    def test_member_view_decoupling(self):
        frame = ctk.CTkFrame(self.root)
        gov_api = MagicMock()
        gov_api.network_mode = 'archon'
        gov_api.archon_id = "test_local_id"
        gov_api.share_banned_list = []

        mv = MemberView(frame, gov_api=gov_api, local_id="test_local_id")
        mv.add_member("remote_node_1", "Node One")
        self.assertIn("remote_node_1", mv.member_labels)

        # Talking state update
        mv.update_talking_state("remote_node_1", 2000.0)
        
        # Ping stats update
        mv.update_stats("remote_node_1", 45)

        # Disconnect status
        toast_cb = MagicMock()
        mv.update_status("remote_node_1", "disconnected", toast_callback=toast_cb)
        self.assertNotIn("remote_node_1", mv.member_labels)
        toast_cb.assert_called_once()
        frame.destroy()

    def test_ui_manager_orchestration(self):
        engine = MagicMock()
        core_api = MagicMock()
        core_api.callsign_map = {}
        core_api.get_local_id.return_value = "local_node_test_id_12345"
        gov_api = MagicMock()
        chat_mgr = MagicMock()
        file_mgr = MagicMock()
        media_ctrl = MagicMock()
        media_ctrl.inputs_map = {"Default Mic": 0}
        media_ctrl.outputs_map = {"Default Speaker": 0}
        media_ctrl.change_mic_mode.return_value = "open_mic"
        loop = MagicMock()
        local_video = MagicMock()

        self.root.show_id_selection = MagicMock()

        mgr = UIManager(self.root, engine, core_api, gov_api, chat_mgr, file_mgr, media_ctrl, loop, local_video)
        mgr.build_top_bar()
        self.assertIsNotNone(mgr.top_bar)
        self.assertIsNotNone(mgr.mic_btn) # Property delegation test

        work_frame = ctk.CTkFrame(self.root)
        mgr.build_node_ui(work_frame)
        self.assertIsNotNone(mgr.member_view)

        # Test exit_room cleanup
        mgr.exit_room()
        self.assertIsNone(mgr.top_bar)
        self.root.show_id_selection.assert_called_once()
        work_frame.destroy()


if __name__ == "__main__":
    unittest.main()
