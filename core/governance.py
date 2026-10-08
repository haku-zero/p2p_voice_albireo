import asyncio
import json
import uuid
import time
from utils.events import event_bus

class GovernanceManager:
    def __init__(self, engine):
        self.engine = engine
        event_bus.on("network_message_received", self.handle_message)
        self.network_mode = None  # None | 'democracy' | 'archon'
        self.archon_id = None
        self.banned_list = set()
        self.share_banned_list = set()
        
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
        if msg_type not in ["sync_net_meta", "cmd_share_permit", "vote_kick_start", "vote_cast", "cmd_banish", "set_heir"]:
            return
            
        if msg_type == "sync_net_meta":
            if self.network_mode is None:
                self.network_mode = data.get("mode")
                self.archon_id = data.get("archon_id")
            banned = data.get("banned_list", [])
            share_banned = data.get("share_banned_list", [])
            self.banned_list.update(banned)
            self.share_banned_list.update(share_banned)
            if getattr(self.engine, "local_id", None) in self.banned_list:
                self.engine.reset()
                
        elif msg_type == "cmd_banish":
            sender = data.get("sender")
            target = data.get("target")
            msg_id = data.get("msg_id")
            if msg_id and msg_id in self.engine.chat_seen: return
            if msg_id: self.engine.chat_seen.add(msg_id)
            
            if self.network_mode == 'archon' and sender == self.archon_id:
                self.banned_list.add(target)
                if getattr(self.engine, "local_id", None) == target:
                    self.engine.reset()
                    return
                elif target in self.engine.connections:
                    self.engine.connections[target].close()
                    
                self._relay(data, current_id)
                
        elif msg_type == "cmd_share_permit":
            sender = data.get("sender")
            target = data.get("target")
            allow = data.get("allow")
            if self.network_mode == 'archon' and sender == self.archon_id:
                if allow:
                    self.share_banned_list.discard(target)
                else:
                    self.share_banned_list.add(target)
                    if getattr(self.engine, "local_id", None) == target:
                        if self.engine.local_video.sharing:
                            event_bus.emit("toast", "Screen Share Revoked by Archon.")
                            self.engine.toggle_screen_share()
                self._relay(data, current_id)
                
        elif msg_type == "vote_kick_start":
            print(f"[Gov] Received vote_kick_start! target={data.get('target')}")
            target = data.get("target")
            vote_id = data.get("vote_id")
            if vote_id in self.engine.chat_seen: return
            self.engine.chat_seen.add(vote_id)
            
            if target in self.immunity_list and time.time() < self.immunity_list[target]:
                return
                
            self.active_votes[target] = {"vote_id": vote_id, "end_time": time.time() + 60, "yes": set(), "no": set()}
            self._relay(data, current_id)
            
            if getattr(self.engine, "local_id", None) != target:
                event_bus.emit("vote_requested", target, vote_id)
            asyncio.run_coroutine_threadsafe(self._tally_vote(target, vote_id), self.engine.loop)
            
        elif msg_type == "vote_cast":
            vote_id = data.get("vote_id")
            target = data.get("target")
            voter = data.get("voter")
            choice = data.get("choice")
            msg_id = data.get("msg_id")
            if msg_id in self.engine.chat_seen: return
            self.engine.chat_seen.add(msg_id)
            
            if target in self.active_votes and self.active_votes[target]["vote_id"] == vote_id:
                if choice == "yes": self.active_votes[target]["yes"].add(voter)
                else: self.active_votes[target]["no"].add(voter)
                
            self._relay(data, current_id)
            
        elif msg_type == "election_vote":
            round_num = data.get("round")
            voter = data.get("voter")
            candidate = data.get("candidate")
            msg_id = data.get("msg_id")
            if msg_id in self.engine.chat_seen: return
            self.engine.chat_seen.add(msg_id)
            
            if self.election_active and round_num == self.election_round:
                self.election_votes[voter] = candidate
            self._relay(data, current_id)

        elif msg_type == "set_heir":
            sender = data.get("sender")
            heir = data.get("heir")
            if self.network_mode == 'archon' and sender == self.archon_id:
                self.designated_heir = heir
            self._relay(data, current_id)

    def on_peer_disconnected(self, peer_id):
        if self.network_mode == 'archon' and peer_id == self.archon_id:
            print(f"[Governance] Archon {peer_id} disconnected!")
            self._trigger_succession()

    def _relay(self, data, skip_id):
        payload_bytes = json.dumps(data).encode('utf-8')
        for rid, ch in self.engine.channels.items():
            if rid != skip_id and ch.readyState == "open":
                ch.send(payload_bytes)
                
    def _broadcast(self, data):
        data["callsign"] = self.engine.callsign
        signed_data = self.engine.crypto.sign_payload(data)
        payload_bytes = json.dumps(signed_data).encode('utf-8')
        for rid, ch in self.engine.channels.items():
            if ch.readyState == "open":
                ch.send(payload_bytes)

    def issue_archon_banish(self, target_id):
        if self.network_mode == 'archon' and self.archon_id == getattr(self.engine, "local_id", None):
            self.banned_list.add(target_id)
            if target_id in self.engine.connections:
                self.engine.connections[target_id].close()
            msg_id = str(uuid.uuid4())
            self.engine.chat_seen.add(msg_id)
            payload = {"type": "cmd_banish", "msg_id": msg_id, "sender": getattr(self.engine, "local_id", None), "target": target_id}
            self._broadcast(payload)

    def issue_share_permit(self, target_id, allow):
        if self.network_mode == 'archon' and self.archon_id == getattr(self.engine, "local_id", None):
            payload = {"type": "cmd_share_permit", "sender": getattr(self.engine, "local_id", None), "target": target_id, "allow": allow}
            self._broadcast(payload)
            if allow:
                self.share_banned_list.discard(target_id)
            else:
                self.share_banned_list.add(target_id)
                if getattr(self.engine, "local_id", None) == target_id:
                    if self.engine.local_video.sharing:
                        self.engine.toggle_screen_share()

    def issue_vote_kick(self, target_id):
        if target_id in self.immunity_list and time.time() < self.immunity_list[target_id]:
            print("Vote blocked by immunity")
            return
        if time.time() - self.last_vote_initiated_time < 300:
            print("Vote blocked by timeout")
            return
        self.last_vote_initiated_time = time.time()
        vote_id = str(uuid.uuid4())
        local_id = getattr(self.engine, "local_id", None)
        self.active_votes[target_id] = {"vote_id": vote_id, "end_time": time.time() + 60, "yes": set([local_id]), "no": set()}
        payload = {"type": "vote_kick_start", "vote_id": vote_id, "sender": local_id, "target": target_id}
        self._broadcast(payload)
        asyncio.run_coroutine_threadsafe(self._tally_vote(target_id, vote_id), self.engine.loop)

    def cast_vote(self, target_id, vote_id, choice):
        local_id = getattr(self.engine, "local_id", None)
        if target_id in self.active_votes and self.active_votes[target_id]["vote_id"] == vote_id:
            if choice == "yes": self.active_votes[target_id]["yes"].add(local_id)
            else: self.active_votes[target_id]["no"].add(local_id)
            msg_id = str(uuid.uuid4())
            self.engine.chat_seen.add(msg_id)
            payload = {"type": "vote_cast", "msg_id": msg_id, "vote_id": vote_id, "sender": local_id, "target": target_id, "voter": local_id, "choice": choice}
            self._broadcast(payload)

    async def _tally_vote(self, target_id, vote_id):
        await asyncio.sleep(60)
        if target_id not in self.active_votes or self.active_votes[target_id]["vote_id"] != vote_id:
            return
            
        vote_data = self.active_votes.pop(target_id)
        yes_count = len(vote_data["yes"])
        total_eligible = len(self.engine.connections) + 1
        local_id = getattr(self.engine, "local_id", None)
        if target_id in self.engine.connections or target_id == local_id:
            total_eligible -= 1
        if total_eligible <= 0: total_eligible = 1
        
        if yes_count > total_eligible / 2.0:
            print(f"[Democracy] Banishment passed for {target_id}")
            self.banned_list.add(target_id)
            if local_id == target_id:
                self.engine.reset()
            elif target_id in self.engine.connections:
                self.engine.connections[target_id].close()
        else:
            print(f"[Democracy] Banishment failed for {target_id}")
            self.immunity_list[target_id] = time.time() + 600

    def assign_heir(self, target_id):
        if self.network_mode == 'archon' and self.archon_id == getattr(self.engine, "local_id", None):
            self.designated_heir = target_id
            payload = {"type": "set_heir", "sender": self.archon_id, "heir": target_id}
            self._broadcast(payload)
            event_bus.emit("toast", f"Assigned Heir: {target_id}")

    def cast_election_vote(self, candidate_id):
        if not self.election_active: return
        local_id = getattr(self.engine, "local_id", None)
        self.election_votes[local_id] = candidate_id
        msg_id = str(uuid.uuid4())
        self.engine.chat_seen.add(msg_id)
        payload = {"type": "election_vote", "msg_id": msg_id, "sender": local_id, "round": self.election_round, "voter": local_id, "candidate": candidate_id}
        self._broadcast(payload)

    def _trigger_succession(self):
        if self.designated_heir and self.designated_heir in self.engine.connections or self.designated_heir == getattr(self.engine, "local_id", None):
            self.archon_id = self.designated_heir
            self.designated_heir = None
            event_bus.emit("toast", f"Archon Succession: {self.archon_id} inherits the throne.")
            return
            
        self._start_election_round(1, list(self.engine.connections.keys()) + [getattr(self.engine, "local_id", None)])
        
    def _start_election_round(self, round_num, candidates):
        if len(candidates) <= 1:
            if candidates: self.archon_id = candidates[0]
            self.election_active = False
            return
            
        self.election_active = True
        self.election_round = round_num
        self.election_votes = {}
        
        event_bus.emit("election_requested", round_num, candidates)
        asyncio.run_coroutine_threadsafe(self._tally_election(round_num, candidates), self.engine.loop)
        
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
                # Deterministic random draw based on node ID string hash so everyone computes the same winner
                winners.sort(key=lambda x: hashlib.sha256(x.encode()).hexdigest())
                self.archon_id = winners[0]
                self.election_active = False
                event_bus.emit("toast", f"Chaos Draw! Archon Elected: {self.archon_id}!")
            else:
                self._start_election_round(round_num + 1, winners)
