import sys
import os
import time
import uuid
import shlex
import asyncio
import threading
from core.api import CoreAPI
from governance.api import GovernanceAPI
from services.chat.manager import ChatManager
from infrastructure.db import LocalDB
from infrastructure.crypto import CryptoManager
from infrastructure.signaling.mqtt_signaling import MQTTRelay
from utils.events import event_bus
from utils import config

class CliRunner:
    """
    Interactive CLI / REPL Terminal Client for Albireo.
    Runs fully detached from GUI frameworks (CustomTkinter/Tk), providing a lightweight,
    scriptable, and headless-friendly terminal experience for P2P communication.
    """
    def __init__(self, room_code=None, callsign=None, loop=None):
        self.loop = loop or asyncio.new_event_loop()
        self._loop_thread = None
        self._own_loop = (loop is None)
        
        self.db = LocalDB()
        self.crypto = CryptoManager()
        self.core_api = CoreAPI(self.loop, self.db, self.crypto)
        self.engine = self.core_api._engine
        self.engine.core_api_ref = self.core_api
        
        self.gov_api = GovernanceAPI(self.core_api)
        self.chat_mgr = ChatManager(self.core_api, self.db)
        
        cfg = config.load_config()
        effective_callsign = callsign or cfg.get("local_id") or "Zero_CLI"
        self.core_api.set_callsign(effective_callsign)
        
        self.room_code = room_code
        self.relay = None
        self.is_host = False
        self.running = False
        self.active_vote_id = None
        self.host_peer_id = None
        
        # Latest message state tracking
        self.latest_message = None
        self._init_latest_message()
        
        self._init_event_bindings()

    def _init_latest_message(self):
        """Loads the most recent message from LocalDB if available."""
        chats = self.db.get_all_chats()
        if chats:
            last = chats[-1]
            s_key = last["sender_key"]
            csign = self.core_api.callsign_map.get(s_key, s_key[:8])
            is_self = (s_key == self.core_api.local_id)
            self._update_latest_message(
                sender=csign,
                content=last["content"],
                timestamp=last["timestamp"],
                is_self=is_self,
                sender_key=s_key
            )

    def _update_latest_message(self, sender, content, timestamp=None, is_self=False, sender_key=None):
        ts = timestamp if timestamp is not None else time.time()
        self.latest_message = {
            "sender": sender,
            "content": content,
            "timestamp": ts,
            "is_self": is_self,
            "sender_key": sender_key
        }

    def _get_prompt(self):
        """Generates dynamic console prompt with latest message banner if present."""
        if self.latest_message:
            ts_str = time.strftime("%H:%M:%S", time.localtime(self.latest_message["timestamp"]))
            sender_str = f"{self.latest_message['sender']} (You)" if self.latest_message.get("is_self") else self.latest_message['sender']
            msg_preview = self.latest_message['content'].replace("\n", " ")
            if len(msg_preview) > 35:
                msg_preview = msg_preview[:32] + "..."
            return f"[📌 最新消息: {ts_str} {sender_str}]: {msg_preview}\nalbireo> "
        return "albireo> "

    def _init_event_bindings(self):
        event_bus.on("chat_message", self._on_chat_message)
        event_bus.on("status", self._on_peer_status)
        event_bus.on("toast", self._on_toast)
        event_bus.on("vote_requested", self._on_vote_requested)
        event_bus.on("election_requested", self._on_election_requested)
        event_bus.on("room_ended_by_archon", self._on_room_ended)
        event_bus.on("all_disconnected", self._on_all_disconnected)
        event_bus.on("peer_ghost_state", self._on_peer_ghost)

    def _print(self, message):
        """Thread-safe and clean console printer."""
        sys.stdout.write(f"\r{message}\n")
        if self.running:
            sys.stdout.write(self._get_prompt())
        sys.stdout.flush()

    def _on_chat_message(self, sender_callsign, content):
        self._update_latest_message(sender_callsign, content, is_self=False)
        self._print(f"💬 [{sender_callsign}]: {content}")

    def _on_peer_status(self, peer_id, status):
        csign = self.core_api.callsign_map.get(peer_id, peer_id[:8])
        self._print(f"🌐 [Network] Peer '{csign}' ({peer_id[:8]}...) is now {status.upper()}.")

    def _on_toast(self, msg):
        self._print(f"🔔 [Notice] {msg}")

    def _on_peer_ghost(self, peer_id, is_ghost):
        if is_ghost:
            self._print(f"⚠️ [Network] Peer {peer_id[:8]}... entered 15s Ghost Grace Period (Reconnecting).")
        else:
            self._print(f"✨ [Network] Peer {peer_id[:8]}... recovered from Ghost State.")

    def _on_vote_requested(self, target, vote_id):
        self.active_vote_id = (target, vote_id)
        self._print(f"⚖️ [Governance] Vote-Kick requested for {target[:8]}... (Vote ID: {vote_id[:8]}). Type '/vote {target[:8]} yes' or '/vote {target[:8]} no'")

    def _on_election_requested(self, round_num, candidates):
        c_list = ", ".join([c[:8] for c in candidates])
        self._print(f"🗳️ [Election] Round {round_num} Active! Candidates: [{c_list}]. Type '/elect <candidate_id>'")

    def _on_room_ended(self):
        self._print("🛑 [Room] Room was forcibly disbanded by the Archon.")
        self.leave_room()

    def _on_all_disconnected(self):
        self._print("📡 [Room] All peers disconnected.")

    def _run_async_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def start(self):
        self.running = True
        if self._own_loop and (self._loop_thread is None or not self._loop_thread.is_alive()):
            self._loop_thread = threading.Thread(target=self._run_async_loop, daemon=True)
            self._loop_thread.start()

        self._print_banner()

        if self.room_code:
            self._print(f"Connecting to room {self.room_code}...")
            self.join_room(self.room_code)

        self._repl_loop()

    def _print_banner(self):
        local_id = self.core_api.get_local_id()
        print("=" * 64)
        print("🌌  Albireo P2P Voice & Mesh — Interactive Terminal Shell (CLI)")
        print(f"🆔  Public Key: {local_id[:16]}...{local_id[-8:]}")
        print(f"🏷️   Callsign:   {self.core_api.get_callsign()}")
        print(f"🛡️   E2EE:       {'Enabled (Ed25519 / X25519)' if self.crypto.enabled else 'Disabled'}")
        print("Type '/help' for a list of available commands. Type '/quit' to exit.")
        print("=" * 64)

    def _repl_loop(self):
        while self.running:
            try:
                sys.stdout.write(self._get_prompt())
                sys.stdout.flush()
                line = sys.stdin.readline()
                if not line:
                    break
                line = line.strip()
                if not line:
                    continue

                output = self.execute_command(line)
                if output:
                    print(output)
            except (KeyboardInterrupt, EOFError):
                print("\n[CLI] Interrupted. Exiting...")
                break
            except Exception as e:
                print(f"[CLI Error] {e}")

        self.stop()

    def execute_command(self, line: str) -> str:
        """Parses and executes a command string synchronously or thread-safely."""
        if not line:
            return ""

        if not line.startswith("/"):
            # Plain message -> Send to chat if in a room
            if self.room_code:
                self.chat_mgr.send_chat(line)
                self._update_latest_message(
                    sender=self.core_api.get_callsign(),
                    content=line,
                    is_self=True,
                    sender_key=self.core_api.local_id
                )
                return f"💬 [You]: {line}"
            else:
                return "⚠️ Not in a room. Use '/join <room_code>' or '/host <room_code>' first."

        parts = shlex.split(line)
        cmd = parts[0].lower()
        args = parts[1:]

        if cmd in ["/help", "/h", "/?"]:
            return self._help_text()

        elif cmd in ["/history", "/chats", "/logs"]:
            chats = self.db.get_all_chats()
            if not chats:
                return "No chat history found for this session."
                
            limit = 20
            if args:
                arg_val = args[0].lower()
                if arg_val == "all":
                    limit = len(chats)
                else:
                    try:
                        limit = int(arg_val)
                    except ValueError:
                        return "Usage: /history [limit_number|all]"
                        
            display_chats = chats[-limit:] if limit > 0 else chats
            lines = [f"--- [Chat History (Last {len(display_chats)} messages)] ---"]
            for c in display_chats:
                ts = time.strftime("%H:%M:%S", time.localtime(c["timestamp"]))
                s_key = c["sender_key"]
                csign = self.core_api.callsign_map.get(s_key, s_key[:8])
                if s_key == self.core_api.local_id:
                    sender_tag = f"{csign} (You)"
                else:
                    sender_tag = f"{csign} [{s_key[:8]}...]"
                lines.append(f"[{ts}] {sender_tag}: {c['content']}")
            lines.append("-" * 44)
            return "\n".join(lines)

        elif cmd in ["/last", "/latest"]:
            if not self.latest_message:
                return "No messages received or sent yet."
            ts_str = time.strftime("%H:%M:%S", time.localtime(self.latest_message["timestamp"]))
            sender_str = f"{self.latest_message['sender']} (You)" if self.latest_message.get("is_self") else self.latest_message['sender']
            elapsed = int(time.time() - self.latest_message["timestamp"])
            ago_str = f"{elapsed}s ago" if elapsed < 60 else f"{elapsed // 60}m ago"
            return f"📌 [Latest Message] [{ts_str} ({ago_str})] {sender_str}: {self.latest_message['content']}"

        elif cmd == "/sync":
            if not self.room_code:
                return "⚠️ Not in a room."
            if self.is_host:
                return "You are the Host (Archon). Other peers sync chat history from you."
            conns = self.core_api.get_connections()
            target = self.host_peer_id or (conns[0] if conns else None)
            if not target:
                return "No peers connected to sync history from."
            self.chat_mgr.request_sync(target)
            return f"Requested chat history sync from host ({target[:8]}...)."

        elif cmd == "/status" or cmd == "/info":
            conns = self.core_api.get_connections()
            return (
                f"--- [Node Status] ---\n"
                f"Room:        {self.room_code or 'None'}\n"
                f"Role:        {'Host' if self.is_host else 'Peer'}\n"
                f"Callsign:    {self.core_api.get_callsign()}\n"
                f"Public Key:  {self.core_api.get_local_id()}\n"
                f"Archon:      {self.gov_api.state.archon_id or 'None'}\n"
                f"Mode:        {self.gov_api.state.network_mode or 'None'}\n"
                f"Peers:       {len(conns)} connected"
            )

        elif cmd in ["/members", "/who", "/list"]:
            conns = self.core_api.get_connections()
            if not conns:
                return "No peers connected in this room."
            lines = ["Connected Peers:"]
            for cid in conns:
                csign = self.core_api.callsign_map.get(cid, "Unknown")
                is_archon = " (Archon)" if cid == self.gov_api.state.archon_id else ""
                lines.append(f"  • {csign} [{cid[:12]}...]{is_archon}")
            return "\n".join(lines)

        elif cmd == "/join":
            if not args:
                return "Usage: /join <room_code>"
            room = args[0].strip()
            self.join_room(room)
            return f"Initiating join to room '{room}' via MQTT Relay..."

        elif cmd == "/host":
            room = args[0].strip() if args else uuid.uuid4().hex[:6].upper()
            mode = args[1].lower() if len(args) > 1 else 'archon'
            self.host_room(room, mode=mode)
            return f"Hosting room '{room}' in {mode.upper()} mode. Share this room code with peers."

        elif cmd == "/leave":
            if not self.room_code:
                return "Not currently in any room."
            r = self.room_code
            self.leave_room()
            return f"Left room '{r}'."

        elif cmd in ["/say", "/msg"]:
            if not args:
                return "Usage: /say <message>"
            msg = " ".join(args)
            if not self.room_code:
                return "⚠️ Not in a room. Use '/join <room>' or '/host <room>' first."
            self.chat_mgr.send_chat(msg)
            self._update_latest_message(
                sender=self.core_api.get_callsign(),
                content=msg,
                is_self=True,
                sender_key=self.core_api.local_id
            )
            return f"💬 [You]: {msg}"

        elif cmd == "/callsign" or cmd == "/nick":
            if not args:
                return f"Current callsign: {self.core_api.get_callsign()}"
            new_cs = args[0]
            self.core_api.set_callsign(new_cs)
            return f"Callsign updated to '{new_cs}'."

        elif cmd == "/kick":
            if not args:
                return "Usage: /kick <peer_id_or_prefix>"
            target = self._resolve_peer_id(args[0])
            if not target:
                return f"Peer '{args[0]}' not found."
            if self.gov_api.state.network_mode == 'archon' and self.gov_api.state.is_archon:
                self.gov_api.state.issue_archon_banish(target)
                return f"Archon banished peer {target[:8]}..."
            else:
                self.gov_api.state.issue_vote_kick(target)
                return f"Initiated vote-kick proposal for peer {target[:8]}..."

        elif cmd == "/ban":
            if not args:
                return "Usage: /ban <peer_id_or_prefix>"
            target = self._resolve_peer_id(args[0])
            if not target:
                return f"Peer '{args[0]}' not found."
            self.gov_api.state.issue_archon_banish(target)
            return f"Banish command issued for {target[:8]}..."

        elif cmd == "/vote":
            if len(args) < 2:
                return "Usage: /vote <target_id_or_prefix> <yes|no>"
            target = self._resolve_peer_id(args[0])
            choice = args[1].lower()
            if choice not in ["yes", "no"]:
                return "Choice must be 'yes' or 'no'."
            
            # Find active vote
            vote_id = None
            if target in self.gov_api.state.active_votes:
                vote_id = self.gov_api.state.active_votes[target]["vote_id"]
            elif self.active_vote_id and self.active_vote_id[0] == target:
                vote_id = self.active_vote_id[1]
                
            if not vote_id:
                return f"No active vote found for {args[0]}."
                
            self.gov_api.cast_vote(target, vote_id, choice)
            return f"Cast '{choice}' vote for target {target[:8]}..."

        elif cmd == "/heir":
            if not args:
                return "Usage: /heir <peer_id_or_prefix>"
            target = self._resolve_peer_id(args[0])
            if not target:
                return f"Peer '{args[0]}' not found."
            self.gov_api.state.assign_heir(target)
            return f"Designated peer {target[:8]}... as the Archon Heir."

        elif cmd == "/elect":
            if not args:
                return "Usage: /elect <candidate_id_or_prefix>"
            target = self._resolve_peer_id(args[0])
            if not target:
                return f"Candidate '{args[0]}' not found."
            self.gov_api.state.cast_election_vote(target)
            return f"Voted for candidate {target[:8]}... in current election round."

        elif cmd == "/end":
            self.gov_api.state.issue_end_room()
            self.leave_room()
            return "Room disbanded."

        elif cmd == "/clear":
            if args and args[0].lower() == "history":
                self.db.clear_chat_history()
                self.latest_message = None
                return "Chat history cleared."
            os.system('cls' if os.name == 'nt' else 'clear')
            return ""

        elif cmd in ["/quit", "/exit"]:
            self.running = False
            return "Exiting Albireo CLI..."

        else:
            return f"Unknown command: '{cmd}'. Type '/help' for available commands."

    def _resolve_peer_id(self, identifier):
        """Resolves full public key by exact match, prefix, or callsign."""
        identifier = identifier.strip()
        conns = self.core_api.get_connections()
        # Direct match
        if identifier in conns:
            return identifier
        # Prefix match
        matches = [cid for cid in conns if cid.startswith(identifier)]
        if len(matches) == 1:
            return matches[0]
        # Callsign match
        for cid in conns:
            if self.core_api.callsign_map.get(cid, "").lower() == identifier.lower():
                return cid
        return None

    def join_room(self, room_code):
        if self.relay:
            self.relay.stop()
            self.relay = None
            
        self.room_code = room_code
        self.engine.room_code = room_code
        self.is_host = False
        
        self.relay = MQTTRelay(room_code, self.core_api.local_id)
        self.relay.start()
        
        def on_answer(sdp_b64, sender):
            def done(remote_id, err_msg):
                if not err_msg:
                    self.host_peer_id = remote_id
                    self._print(f"🔗 [Linked] Connected to host {remote_id[:8]}...!")
                    # Auto sync chat history from Host
                    self.chat_mgr.request_sync(remote_id)
                    if self.relay:
                        self.relay.stop()
            asyncio.run_coroutine_threadsafe(self.engine.client_accept_answer(sdp_b64, done), self.loop)
            
        self.relay.on_answer_received = on_answer
        
        def offer_done(offer_str, err):
            if not err and self.relay:
                self.relay.send_offer("all", offer_str)
                self._print("📡 [Signaling] Offer broadcasted. Waiting for Answer...")
                
        asyncio.run_coroutine_threadsafe(self.engine.client_generate_offer(offer_done), self.loop)

    def host_room(self, room_code, mode='archon'):
        if self.relay:
            self.relay.stop()
            self.relay = None
            
        self.room_code = room_code
        self.engine.room_code = room_code
        self.is_host = True
        self.engine.is_host = True
        
        self.gov_api.state.network_mode = mode
        if mode == 'archon':
            self.gov_api.state.archon_id = self.core_api.local_id
            
        self.relay = MQTTRelay(room_code, self.core_api.local_id)
        
        def on_offer(sdp_b64, sender):
            def done(ans_str, remote_id, err):
                if not err and self.relay:
                    self.relay.send_answer(sender, ans_str)
                    self._print(f"🔗 [Linked] Inbound connection established with peer {remote_id[:8]}...!")
            asyncio.run_coroutine_threadsafe(self.engine.host_accept_offer(sdp_b64, done), self.loop)
            
        self.relay.on_offer_received = on_offer
        self.relay.start()

    def leave_room(self):
        try:
            self.core_api.broadcast_message({"type": "peer_left", "peer_id": self.core_api.local_id})
        except Exception:
            pass
        if self.relay:
            self.relay.stop()
            self.relay = None
        self.room_code = None
        self.is_host = False
        self.host_peer_id = None
        self.db.clear_chat_history()
        self.core_api.reset_node()
        self.latest_message = None

    def stop(self):
        self.running = False
        self.leave_room()
        if self._own_loop and self.loop.is_running():
            async def _cleanup():
                tasks = [t for t in asyncio.all_tasks(self.loop) if t is not asyncio.current_task()]
                for t in tasks:
                    t.cancel()
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
                self.loop.stop()
            asyncio.run_coroutine_threadsafe(_cleanup(), self.loop)

    def _help_text(self):
        return """
Available CLI Commands:
  /help, /h               Show this help manual
  /join <room_code>       Join an existing Albireo room via encrypted MQTT relay
  /host [room_code]       Host a new room (optional: [archon|democracy] mode)
  /leave                  Disconnect and leave current room
  /say <message>          Broadcast an E2EE chat message to the room (or just type text)
  /history [n|all]        Display chat history (default: last 20 messages, aliases: /chats, /logs)
  /last, /latest          Display the most recent message received or sent
  /sync                   Request full chat history re-sync from room host
  /members, /who          List all connected peers in current room
  /status, /info          Show local identity, public key, room, and network stats
  /nick <new_callsign>    Update local display callsign
  /kick <peer_id>         Propose a vote-kick (Democracy) or banish immediately (Archon)
  /ban <peer_id>          [Archon] Banish a peer immediately
  /vote <peer_id> <y|n>   Vote yes or no on an active kick proposal
  /heir <peer_id>         [Archon] Designate a succession heir
  /elect <candidate_id>   Cast vote in a headless consensus election
  /end                    [Archon] Forcibly disband the room
  /clear [history]        Clear console screen or clear chat history (/clear history)
  /quit, /exit            Quit and terminate the client
"""
