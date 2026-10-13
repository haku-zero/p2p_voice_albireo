import threading

class Events:
    """
    Standardized Event Names and Payload Contracts for Albireo EventBus.
    See ARCHITECTURE.md Section 3 for full specifications.
    """
    # Network & Lifecycle
    STATUS = "status"                          # (peer_id: str, status: "connected" | "disconnected")
    PEER_LEFT = "peer_left"                    # (peer_id: str)
    PEER_JOINED = "peer_joined"                # (peer_id: str)
    PEER_GHOST_STATE = "peer_ghost_state"      # (peer_id: str, is_ghost: bool)
    PEER_CALLSIGN_UPDATED = "peer_callsign_updated"  # (peer_id: str, callsign: str)
    ROSTER_UPDATED = "roster_updated"          # (roster: list[str])
    ALL_DISCONNECTED = "all_disconnected"      # ()
    
    # Audio & Hardware
    LOCAL_MIC_LEVEL = "local_mic_level"        # (rms: float)
    TALKING = "talking"                        # (peer_id: str, rms: float)
    STATS = "stats"                            # (peer_id: str, ping: int)
    
    # Messaging & File Transfer
    CHAT_MESSAGE = "chat_message"              # (sender_callsign: str, content: str)
    FILE_INCOMING = "file_incoming"            # (peer_id: str, filename: str, size: int, file_id: str)
    FILE_PROGRESS = "file_progress"            # (peer_id: str, progress: float, file_id: str)
    FILE_DONE = "file_done"                    # (peer_id: str, filename: str, path: str, file_id: str)
    
    # Video & Screen Sharing
    VIDEO_FRAME = "video_frame"                # (peer_id: str, arr: np.ndarray)
    VIDEO_STOPPED = "video_stopped"            # (peer_id: str)
    SFU_MIGRATION = "sfu_migration_triggered"  # (new_host_id: str)
    
    # Governance & Modals
    VOTE_REQUESTED = "vote_requested"          # (target: str, vote_id: str)
    ELECTION_REQUESTED = "election_requested"  # (round_num: int, candidates: list[str])
    ROOM_ENDED = "room_ended_by_archon"        # ()
    TOAST = "toast"                            # (message: str)

class EventEmitter:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(EventEmitter, cls).__new__(cls)
                cls._instance.listeners = {}
        return cls._instance

    def on(self, event, callback):
        with self._lock:
            if event not in self.listeners:
                self.listeners[event] = []
            if callback not in self.listeners[event]:
                self.listeners[event].append(callback)

    def off(self, event, callback):
        with self._lock:
            if event in self.listeners and callback in self.listeners[event]:
                self.listeners[event].remove(callback)

    def emit(self, event, *args, **kwargs):
        callbacks = []
        with self._lock:
            if event in self.listeners:
                callbacks = list(self.listeners[event])
                
        for callback in callbacks:
            try:
                callback(*args, **kwargs)
            except Exception as e:
                print(f"[EventBus] Error in handler for '{event}': {e}")

event_bus = EventEmitter()
