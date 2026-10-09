from .state import GovernanceManager

class GovernanceAPI:
    """
    Facade for the Governance module.
    Exposes high-level actions (e.g. vote_kick) to the UI, while managing its own
    decentralized state using the underlying CoreAPI.
    """
    def __init__(self, core_api):
        self.core_api = core_api
        self.state = GovernanceManager(self.core_api)
        
        # Wire up core hooks to feed data into governance (Inside-Out)
        self.core_api.set_auth_hook(self.state.is_banned)
        self.core_api.set_meta_hook(self._generate_meta)
        self.core_api.register_disconnect_handler(self.state.on_peer_disconnected)
        self.core_api.register_message_handler(self._handle_network_message)
        
        from utils.events import event_bus
        event_bus.on("network_status", self._on_network_status)
        
    def _on_network_status(self, peer_id, status):
        if status == "connected" and self.state.is_archon and self.core_api.crypto.enabled:
            if not self.core_api.crypto.room_key:
                self.core_api.crypto.generate_room_key()
            
            encrypted_key = self.core_api.crypto.encrypt_room_key_for_peer(peer_id)
            if encrypted_key:
                self.core_api.send_on_channel(peer_id, "control", {
                    "type": "e2ee_key_dist",
                    "key": encrypted_key
                })

    def _handle_network_message(self, peer_id, label, data):
        if label != "control": return
        if data.get("type") == "e2ee_key_dist":
            if peer_id == self.state.archon_id:
                success = self.core_api.crypto.decrypt_room_key(peer_id, data["key"])
                if success:
                    from utils.events import event_bus
                    event_bus.emit("toast", "E2EE Room Key Established")

    def _generate_meta(self):
        if self.state.network_mode is not None:
            return {
                "type": "sync_net_meta",
                "mode": self.state.network_mode,
                "archon_id": self.state.archon_id,
                "banned_list": list(self.state.banned_list),
                "share_banned_list": list(self.state.share_banned_list)
            }
        return None

    # --- Actions Exposed to UI ---
    
    def issue_vote_kick(self, target_id):
        self.state.issue_vote_kick(target_id)
        
    def cast_vote(self, target_id, vote_id, choice):
        self.state.cast_vote(target_id, vote_id, choice)
        
    def issue_archon_banish(self, target_id):
        self.state.issue_archon_banish(target_id)
        
    def issue_end_room(self):
        self.state.issue_end_room()
        
    def assign_heir(self, target_id):
        self.state.assign_heir(target_id)
        
    def cast_election_vote(self, candidate_id):
        self.state.cast_election_vote(candidate_id)
        
    def issue_share_permit(self, target_id, allow):
        self.state.issue_share_permit(target_id, allow)
        
    # --- State Readers ---
    @property
    def network_mode(self):
        return self.state.network_mode
        
    @network_mode.setter
    def network_mode(self, value):
        self.state.network_mode = value
        
    @property
    def archon_id(self):
        return self.state.archon_id
        
    @archon_id.setter
    def archon_id(self, value):
        self.state.archon_id = value
