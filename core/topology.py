import asyncio
from utils.events import event_bus

class TopologyManager:
    """
    Data Plane Selection Algorithm Module.
    Manages dynamic SFU election, backup rosters, and fault tolerance (Host Migration).
    """
    def __init__(self, engine, core_api_ref):
        self.engine = engine
        self.core_api = core_api_ref
        self.active_roster = []
        self._heartbeat_task = None

    def start(self):
        self._heartbeat_task = self.engine.loop.create_task(self._heartbeat_loop())

    def stop(self):
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            self._heartbeat_task = None

    def handle_roster_update(self, roster):
        """Called when a roster message is received from the current SFU."""
        self.active_roster = roster

    async def _heartbeat_loop(self):
        """Host periodically broadcasts the connected peer list as a failover roster."""
        while True:
            await asyncio.sleep(5)
            if getattr(self.engine, "is_host", False):
                # Data Plane Selection Algorithm (Base): Currently sorts by Public Key (Lexicographical)
                # This guarantees 100% deterministic consensus across all nodes without negotiation.
                # In the future, this can sort by ping/latency scores.
                roster = list(self.engine.connections.keys()) + [self.core_api.local_id]
                roster.sort()
                self.active_roster = roster
                self.core_api.broadcast_message({"type": "roster", "roster": roster})

    def elect_next_sfu(self, dead_host_id):
        """Core Algorithm to select the next SFU."""
        backup_list = [p for p in self.active_roster if p != dead_host_id]
        if not backup_list:
            return None
        return backup_list[0]

    def trigger_migration(self, dead_host_id):
        if not self.active_roster:
            print("[Topology] No roster available, cannot migrate.")
            return

        new_host_id = self.elect_next_sfu(dead_host_id)
        if not new_host_id:
            return

        room_code = getattr(self.engine, "room_code", None)
        if not room_code: 
            return

        event_bus.emit("toast", f"SFU Offline! Migrating to [{new_host_id[:8]}] in 2s...")
        print(f"[Topology] Elected new SFU: {new_host_id}")

        def _execute_migration():
            event_bus.emit("sfu_migration_triggered", new_host_id)
            
        # Wait a moment for TCP/MQTT to clear out
        self.engine.loop.call_later(2.0, _execute_migration)
