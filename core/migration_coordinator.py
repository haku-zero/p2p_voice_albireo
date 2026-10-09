import asyncio
from utils.events import event_bus
from infrastructure.signaling.mqtt_signaling import MQTTRelay

class MigrationCoordinator:
    """
    Coordinates the complex process of SFU host migration.
    Decouples the election logic (topology.py) from the actual network reconnection
    and voice mixer reconfiguration steps.
    """
    def __init__(self, core_api):
        self.api = core_api
        event_bus.on("sfu_migration_triggered", self.on_migration_triggered)

    def on_migration_triggered(self, new_host_id):
        engine = self.api._engine
        room_code = getattr(engine, "room_code", None)
        if not room_code:
            return

        if self.api.local_id == new_host_id:
            # I am the new Host!
            engine.is_host = True
            

            self.api.relay = MQTTRelay(room_code, self.api.local_id)
            def on_offer(sdp_b64, sender):
                def done(ans_str, remote_id, err):
                    if not err: self.api.relay.send_answer(sender, ans_str)
                asyncio.run_coroutine_threadsafe(engine.host_accept_offer(sdp_b64, done), engine.loop)
            self.api.relay.on_offer_received = on_offer
            self.api.relay.start()
            
        else:
            # I am still a client, connect to new Host
            self.api.relay = MQTTRelay(room_code, self.api.local_id)
            self.api.relay.start()
            def on_answer(sdp_b64, sender):
                def done(remote_id, err_msg):
                    self.api.relay.stop()
                asyncio.run_coroutine_threadsafe(engine.client_accept_answer(sdp_b64, done), engine.loop)
            self.api.relay.on_answer_received = on_answer
            def offer_done(offer_str, err):
                if not err: self.api.relay.send_offer("all", offer_str)
            asyncio.run_coroutine_threadsafe(engine.client_generate_offer(offer_done), engine.loop)
