import asyncio
import uuid
import time
from utils.events import event_bus

class GovernanceManager:
    def __init__(self, core_api):
        self.core_api = core_api
        self.network_mode = None  # None | 'democracy' | 'archon'
        self.archon_id = None
        self.banned_list = set()
        self.share_banned_list = set()
        self.seen_msgs = set()
        
        # Succession state
        self.designated_heir = None
        self.election_round = 0
        self.election_votes = {} # voter -> candidate
        self.election_active = False

        # Anti-spam
        self.last_vote_initiated_time = 0
        self.immunity_list = {}
        self.active_votes = {}

    def is_banned(self, target_id):
        return target_id in self.banned_list

    def handle_message(self, data, current_id):
        msg_type = data.get("type")
        if msg_type not in ["sync_net_meta", "cmd_share_permit", "vote_kick_start", "vote_cast", "cmd_banish", "set_heir", "cmd_end_room"]:
            return
            
        if msg_type == "sync_net_meta":
            if self.network_mode is None:
                self.network_mode = data.get("mode")
                self.archon_id = data.get("archon_id")
            banned = data.get("banned_list", [])
            share_banned = data.get("share_banned_list", [])
            self.banned_list.update(banned)
            self.share_banned_list.update(share_banned)
            if self.core_api.get_local_id() in self.banned_list:
                self.core_api.reset_node()
                
        elif msg_type == "cmd_banish":
            sender = data.get("sender")
            target = data.get("target")
            msg_id = data.get("msg_id")
            if msg_id and msg_id in self.seen_msgs: return
            if msg_id: self.seen_msgs.add(msg_id)
            
            if self.network_mode == 'archon' and sender == self.archon_id:
                self.banned_list.add(target)
                if self.core_api.get_local_id() == target:
                    self.core_api.reset_node()
                    return
                elif target in self.core_api.get_connections():
                    self.core_api.close_connection(target)
                    
                self.core_api.relay_message(data, current_id)
                
        elif msg_type == "cmd_share_permit":
            sender = data.get("sender")
            target = data.get("target")
            allow = data.get("allow")
            if self.network_mode == 'archon' and sender == self.archon_id:
                if allow:
                    self.share_banned_list.discard(target)
                else:
                    self.share_banned_list.add(target)
                    if self.core_api.get_local_id() == target:
                        if self.core_api.is_screen_sharing():
                            event_bus.emit("toast", "Screen Share Revoked by Archon.")
                            self.core_api.toggle_screen_share()
                self.core_api.relay_message(data, current_id)
                
        elif msg_type == "vote_kick_start":
            print(f"[Gov] Received vote_kick_start! target={data.get('target')}")
            target = data.get("target")
            vote_id = data.get("vote_id")
            if vote_id in self.seen_msgs: return
            self.seen_msgs.add(vote_id)
            
            if target in self.immunity_list and time.time() < self.immunity_list[target]:
                return
                
            self.active_votes[target] = {"vote_id": vote_id, "end_time": time.time() + 60, "yes": set(), "no": set()}
            self.core_api.relay_message(data, current_id)
            
            if self.core_api.get_local_id() != target:
                event_bus.emit("vote_requested", target, vote_id)
            asyncio.run_coroutine_threadsafe(self._tally_vote(target, vote_id), self.core_api.get_event_loop())
            
        elif msg_type == "vote_cast":
            vote_id = data.get("vote_id")
            target = data.get("target")
            voter = data.get("voter")
            choice = data.get("choice")
            msg_id = data.get("msg_id")
            if msg_id and msg_id in self.seen_msgs: return
            if msg_id: self.seen_msgs.add(msg_id)
            
            if target in self.active_votes and self.active_votes[target]["vote_id"] == vote_id:
                if choice == "yes": self.active_votes[target]["yes"].add(voter)
                else: self.active_votes[target]["no"].add(voter)
                
            self.core_api.relay_message(data, current_id)
            
        elif msg_type == "election_vote":
            round_num = data.get("round")
            voter = data.get("voter")
            candidate = data.get("candidate")
            msg_id = data.get("msg_id")
            if msg_id and msg_id in self.seen_msgs: return
            if msg_id: self.seen_msgs.add(msg_id)
            
            if self.election_active and round_num == self.election_round:
                self.election_votes[voter] = candidate
            self.core_api.relay_message(data, current_id)

        elif msg_type == "set_heir":
            sender = data.get("sender")
            heir = data.get("heir")
            if self.network_mode == 'archon' and sender == self.archon_id:
                self.designated_heir = heir
            self.core_api.relay_message(data, current_id)

        elif msg_type == "cmd_end_room":
            sender = data.get("sender")
            msg_id = data.get("msg_id")
            if msg_id and msg_id in self.seen_msgs: return
            if msg_id: self.seen_msgs.add(msg_id)
            
            if self.network_mode == 'archon' and sender == self.archon_id:
                from utils.events import event_bus
                event_bus.emit("room_ended_by_archon")
                self.core_api.relay_message(data, current_id)

    def on_peer_disconnected(self, peer_id):
        if self.network_mode == 'archon' and peer_id == self.archon_id:
            print(f"[Governance] Archon {peer_id} disconnected!")
            self._trigger_succession()

    def issue_archon_banish(self, target_id):
        local_id = self.core_api.get_local_id()
        if self.network_mode == 'archon' and self.archon_id == local_id:
            self.banned_list.add(target_id)
            if target_id in self.core_api.get_connections():
                self.core_api.close_connection(target_id)
            msg_id = str(uuid.uuid4())
            self.seen_msgs.add(msg_id)
            payload = {"type": "cmd_banish", "msg_id": msg_id, "sender": local_id, "target": target_id}
            self.core_api.broadcast_message(payload)

    def issue_end_room(self):
        local_id = self.core_api.get_local_id()
        if self.network_mode == 'archon' and self.archon_id == local_id:
            msg_id = str(uuid.uuid4())
            self.seen_msgs.add(msg_id)
            payload = {"type": "cmd_end_room", "msg_id": msg_id, "sender": local_id}
            self.core_api.broadcast_message(payload)
            from utils.events import event_bus
            event_bus.emit("room_ended_by_archon")

    def issue_share_permit(self, target_id, allow):
        local_id = self.core_api.get_local_id()
        if self.network_mode == 'archon' and self.archon_id == local_id:
            payload = {"type": "cmd_share_permit", "sender": local_id, "target": target_id, "allow": allow}
            self.core_api.broadcast_message(payload)
            if allow:
                self.share_banned_list.discard(target_id)
            else:
                self.share_banned_list.add(target_id)
                if local_id == target_id:
                    if self.core_api.is_screen_sharing():
                        self.core_api.toggle_screen_share()

    def issue_vote_kick(self, target_id):
        if target_id in self.immunity_list and time.time() < self.immunity_list[target_id]:
            print("Vote blocked by immunity")
            return
        if time.time() - self.last_vote_initiated_time < 300:
            print("Vote blocked by timeout")
            return
        self.last_vote_initiated_time = time.time()
        vote_id = str(uuid.uuid4())
        local_id = self.core_api.get_local_id()
        self.active_votes[target_id] = {"vote_id": vote_id, "end_time": time.time() + 60, "yes": set([local_id]), "no": set()}
        payload = {"type": "vote_kick_start", "vote_id": vote_id, "sender": local_id, "target": target_id}
        self.core_api.broadcast_message(payload)
        asyncio.run_coroutine_threadsafe(self._tally_vote(target_id, vote_id), self.core_api.get_event_loop())

    def cast_vote(self, target_id, vote_id, choice):
        local_id = self.core_api.get_local_id()
        if target_id in self.active_votes and self.active_votes[target_id]["vote_id"] == vote_id:
            if choice == "yes": self.active_votes[target_id]["yes"].add(local_id)
            else: self.active_votes[target_id]["no"].add(local_id)
            msg_id = str(uuid.uuid4())
            self.seen_msgs.add(msg_id)
            payload = {"type": "vote_cast", "msg_id": msg_id, "vote_id": vote_id, "sender": local_id, "target": target_id, "voter": local_id, "choice": choice}
            self.core_api.broadcast_message(payload)

    async def _tally_vote(self, target_id, vote_id):
        await asyncio.sleep(60)
        if target_id not in self.active_votes or self.active_votes[target_id]["vote_id"] != vote_id:
            return
            
        vote_data = self.active_votes.pop(target_id)
        yes_count = len(vote_data["yes"])
        total_eligible = len(self.core_api.get_connections()) + 1
        local_id = self.core_api.get_local_id()
        if target_id in self.core_api.get_connections() or target_id == local_id:
            total_eligible -= 1
        if total_eligible <= 0: total_eligible = 1
        
        if yes_count > total_eligible / 2.0:
            print(f"[Democracy] Banishment passed for {target_id}")
            self.banned_list.add(target_id)
            if local_id == target_id:
                self.core_api.reset_node()
            elif target_id in self.core_api.get_connections():
                self.core_api.close_connection(target_id)
        else:
            print(f"[Democracy] Banishment failed for {target_id}")
            self.immunity_list[target_id] = time.time() + 600

    def assign_heir(self, target_id):
        if self.network_mode == 'archon' and self.archon_id == self.core_api.get_local_id():
            self.designated_heir = target_id
            payload = {"type": "set_heir", "sender": self.archon_id, "heir": target_id}
            self.core_api.broadcast_message(payload)
            event_bus.emit("toast", f"Assigned Heir: {target_id}")

    def cast_election_vote(self, candidate_id):
        if not self.election_active: return
        local_id = self.core_api.get_local_id()
        self.election_votes[local_id] = candidate_id
        msg_id = str(uuid.uuid4())
        self.seen_msgs.add(msg_id)
        payload = {"type": "election_vote", "msg_id": msg_id, "sender": local_id, "round": self.election_round, "voter": local_id, "candidate": candidate_id}
        self.core_api.broadcast_message(payload)

    def _trigger_succession(self):
        local_id = self.core_api.get_local_id()
        if self.designated_heir and (self.designated_heir in self.core_api.get_connections() or self.designated_heir == local_id):
            self.archon_id = self.designated_heir
            self.designated_heir = None
            event_bus.emit("toast", f"Archon Succession: {self.archon_id} inherits the throne.")
            return
            
        self._start_election_round(1, self.core_api.get_connections() + [local_id])
        
    def _start_election_round(self, round_num, candidates):
        if len(candidates) <= 1:
            if candidates: self.archon_id = candidates[0]
            self.election_active = False
            return
            
        self.election_active = True
        self.election_round = round_num
        self.election_votes = {}
        
        event_bus.emit("election_requested", round_num, candidates)
        asyncio.run_coroutine_threadsafe(self._tally_election(round_num, candidates), self.core_api.get_event_loop())
        
    async def _tally_election(self, round_num, candidates):
        await asyncio.sleep(30)
        if not self.election_active or self.election_round != round_num: return
        
        tallies = {c: 0 for c in candidates}
        for voter, candidate in self.election_votes.items():
            if candidate in tallies: tallies[candidate] += 1
            
        # Find max votes
        max_votes = max(tallies.values()) if tallies else 0
        winners = [c for c, v in tallies.items() if v == max_votes]
        
        if len(winners) == 1:
            self.archon_id = winners[0]
            self.election_active = False
            event_bus.emit("toast", f"Archon Elected: {self.archon_id}!")
        else:
            if round_num >= 3:
                import hashlib
                # Deterministic random draw
                winners.sort(key=lambda x: hashlib.sha256(x.encode()).hexdigest())
                self.archon_id = winners[0]
                self.election_active = False
                event_bus.emit("toast", f"Chaos Draw! Archon Elected: {self.archon_id}!")
            else:
                self._start_election_round(round_num + 1, winners)
