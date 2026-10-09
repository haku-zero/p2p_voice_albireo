class AppStore:
    """
    A lightweight, centralized state management system (similar to Redux/Vuex).
    Enables one-way data flow: Core -> Dispatch Action -> Store Updates -> UI Re-renders.
    """
    def __init__(self):
        self._state = {
            "members": {}, # { peer_id: { "callsign": str, "status": str, "ping": int, "talking_rms": float } }
            "mic_muted": False,
            "speaker_muted": False,
            "is_sharing": False,
            "volume": 0.1,
            "mic_volume": 1.0
        }
        self._subscribers = []
        
    def subscribe(self, callback):
        """Callback receives (state_dict) on every mutation."""
        self._subscribers.append(callback)
        
    def get_state(self):
        return self._state
        
    def dispatch(self, action_type, payload=None):
        """Mutate state based on action and notify all subscribers."""
        state_changed = False
        
        if action_type == "MEMBER_JOINED":
            pid = payload["peer_id"]
            if pid not in self._state["members"]:
                self._state["members"][pid] = {
                    "callsign": payload.get("callsign", pid[:8]),
                    "status": "connected",
                    "ping": 0,
                    "talking_rms": 0
                }
                state_changed = True
                
        elif action_type == "MEMBER_LEFT":
            pid = payload["peer_id"]
            if pid in self._state["members"]:
                self._state["members"][pid]["status"] = "disconnected"
                state_changed = True
                
        elif action_type == "UPDATE_MEMBER_STATS":
            pid = payload["peer_id"]
            if pid in self._state["members"]:
                if "ping" in payload: self._state["members"][pid]["ping"] = payload["ping"]
                if "rms" in payload: self._state["members"][pid]["talking_rms"] = payload["rms"]
                state_changed = True
                
        elif action_type == "TOGGLE_MIC":
            self._state["mic_muted"] = payload
            state_changed = True
            
        elif action_type == "TOGGLE_SPEAKER":
            self._state["speaker_muted"] = payload
            state_changed = True
            
        elif action_type == "TOGGLE_SHARE":
            self._state["is_sharing"] = payload
            state_changed = True
            
        elif action_type == "SET_VOLUMES":
            if "mic" in payload: self._state["mic_volume"] = payload["mic"]
            if "speaker" in payload: self._state["volume"] = payload["speaker"]
            state_changed = True
            
        if state_changed:
            self._notify()
            
    def _notify(self):
        for sub in self._subscribers:
            sub(self._state)

# Global store singleton
store = AppStore()
