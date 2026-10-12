import hashlib
import json
import asyncio
import uuid
import ssl
import paho.mqtt.client as mqtt

class MQTTRelay:
    def __init__(self, room_code, local_id):
        self.room_code = room_code
        self.local_id = local_id
        
        # Normalize room code (strip dashes, case-insensitive) and hash with salt to prevent rainbow table attacks
        normalized_room = str(room_code).strip().replace("-", "").upper()
        salt = b"albireo_salt_v1_"
        hashed_room = hashlib.sha256(salt + normalized_room.encode('utf-8')).hexdigest()[:24]
        self.topic_base = f"albireo/room/{hashed_room}"
        
        # Paho MQTT v2 requires callback_api_version; append random suffix to avoid broker mutual kick loops
        client_id = f"albireo_{local_id[:8]}_{uuid.uuid4().hex[:6]}"
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        
        from utils import config
        cfg = config.load_config()
        self.use_tls = cfg.get("mqtt_use_tls", True)
        self.broker = cfg.get("mqtt_broker", "broker.emqx.io")
        default_port = 8883 if self.use_tls else 1883
        self.port = cfg.get("mqtt_port", default_port)
        self.connected = False
        
        self.on_offer_received = None
        self.on_answer_received = None
        self.on_knock_received = None
        
    def start(self):
        try:
            if self.use_tls:
                self.client.tls_set()
            self.client.connect(self.broker, self.port, 60)
            self.client.loop_start()
            return True
        except Exception as e:
            print(f"[MQTT] Failed to start relay: {e}")
            return False
        
    def stop(self):
        self.connected = False
        self.client.loop_stop()
        self.client.disconnect()
        
    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            self.connected = True
            print(f"[MQTT] Connected to relay. Subscribing to {self.topic_base}/#")
            self.client.subscribe(f"{self.topic_base}/#")
        else:
            self.connected = False
            print(f"[MQTT] Connection failed with code {reason_code}")

    def _on_message(self, client, userdata, msg):
        topic = msg.topic
        try:
            payload = json.loads(msg.payload.decode('utf-8'))
        except:
            return
            
        sender = payload.get("sender")
        if sender == self.local_id:
            return # Ignore own messages
            
        action = payload.get("action")
        
        if topic.endswith("/knock") and action == "knock" and self.on_knock_received:
            self.on_knock_received(sender)
            
        elif (topic.endswith(f"/offer/{self.local_id}") or topic.endswith("/offer/all")) and action == "offer" and self.on_offer_received:
            self.on_offer_received(payload.get("sdp_b64"), sender)
            
        elif topic.endswith(f"/answer/{self.local_id}") and action == "answer" and self.on_answer_received:
            self.on_answer_received(payload.get("sdp_b64"), sender)

    def send_knock(self):
        payload = {"action": "knock", "sender": self.local_id}
        self.client.publish(f"{self.topic_base}/knock", json.dumps(payload), qos=1)
        
    def send_offer(self, target_id, sdp_b64):
        payload = {"action": "offer", "sender": self.local_id, "sdp_b64": sdp_b64}
        self.client.publish(f"{self.topic_base}/offer/{target_id}", json.dumps(payload), qos=1)
        
    def send_answer(self, target_id, sdp_b64):
        payload = {"action": "answer", "sender": self.local_id, "sdp_b64": sdp_b64}
        self.client.publish(f"{self.topic_base}/answer/{target_id}", json.dumps(payload), qos=1)
