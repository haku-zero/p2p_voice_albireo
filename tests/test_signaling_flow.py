import sys
import os
import time
import asyncio
import unittest

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from core.engine import WebRTCEngine
from infrastructure.signaling.mqtt_signaling import MQTTRelay

class TestSignalingFlow(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def tearDown(self):
        pending = asyncio.all_tasks(self.loop)
        for task in pending:
            task.cancel()
        if pending:
            self.loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        self.loop.close()

    def test_manual_offline_signaling_flow(self):
        """
        验证离线/手动模式下生成 Uplink Offer、Host 计算 Answer 以及 Client 应用 Answer 的全流程。
        解决 AttributeError: 'WebRTCEngine' object has no attribute 'client_generate_offer'。
        """
        host_engine = WebRTCEngine(self.loop)
        host_engine.local_id = "host_node_id"
        host_engine.callsign = "HostNode"

        client_engine = WebRTCEngine(self.loop)
        client_engine.local_id = "client_node_id"
        client_engine.callsign = "ClientNode"

        # 1. Client 生成 Uplink Offer
        offer_holder = {}
        def on_offer_done(offer_str, err):
            offer_holder["offer"] = offer_str
            offer_holder["err"] = err

        self.loop.run_until_complete(client_engine.client_generate_offer(on_offer_done))
        self.assertFalse(offer_holder.get("err"), f"Generate offer failed: {offer_holder.get('offer')}")
        self.assertIsNotNone(offer_holder.get("offer"))
        offer_b64 = offer_holder["offer"]

        # 2. Host 接收 Offer 并生成 Answer
        answer_holder = {}
        def on_answer_done(ans_str, remote_id, err):
            answer_holder["ans"] = ans_str
            answer_holder["remote_id"] = remote_id
            answer_holder["err"] = err

        self.loop.run_until_complete(host_engine.host_accept_offer(offer_b64, on_answer_done))
        self.assertFalse(answer_holder.get("err"), f"Host accept offer failed: {answer_holder.get('ans')}")
        self.assertIsNotNone(answer_holder.get("ans"))
        self.assertEqual(answer_holder["remote_id"], "client_node_id")
        ans_b64 = answer_holder["ans"]

        # 3. Client 接受并设置 Answer
        final_holder = {}
        def on_final_done(remote_id, err):
            final_holder["remote_id"] = remote_id
            final_holder["err"] = err

        self.loop.run_until_complete(client_engine.client_accept_answer(ans_b64, on_final_done))
        self.assertFalse(final_holder.get("err"), f"Client accept answer failed: {final_holder.get('remote_id')}")
        self.assertEqual(final_holder["remote_id"], "host_node_id")

        # 清理连接
        host_engine.reset()
        client_engine.reset()

    def test_mqtt_relay_two_nodes(self):
        """
        验证双节点使用 MQTTRelay 进行信令交换（Offer / Answer 转发），且无 client_id 碰撞互踢。
        """
        test_room = f"test_room_{int(time.time())}"
        host_id = "host_abc12345"
        client_id = "client_xyz67890"

        host_relay = MQTTRelay(test_room, host_id)
        client_relay = MQTTRelay(test_room, client_id)

        received_by_host = []
        received_by_client = []

        host_relay.on_offer_received = lambda sdp_b64, sender: received_by_host.append((sdp_b64, sender))
        client_relay.on_answer_received = lambda sdp_b64, sender: received_by_client.append((sdp_b64, sender))

        try:
            started_host = host_relay.start()
            started_client = client_relay.start()
            self.assertTrue(started_host, "Host MQTT start failed")
            self.assertTrue(started_client, "Client MQTT start failed")

            # 等待双方连接到 Broker 并完成订阅
            for _ in range(50):
                if host_relay.connected and client_relay.connected:
                    break
                time.sleep(0.1)

            self.assertTrue(host_relay.connected, "Host relay did not reach connected state")
            self.assertTrue(client_relay.connected, "Client relay did not reach connected state")
            time.sleep(0.5)

            # Client 发送 Offer
            dummy_offer = "dummy_offer_base64_payload"
            client_relay.send_offer("all", dummy_offer)

            # 等待 Host 接收到 Offer
            for _ in range(30):
                if received_by_host:
                    break
                time.sleep(0.1)

            self.assertTrue(len(received_by_host) > 0, "Host did not receive offer via MQTT")
            self.assertEqual(received_by_host[0][0], dummy_offer)
            self.assertEqual(received_by_host[0][1], client_id)

            # Host 回复 Answer
            dummy_answer = "dummy_answer_base64_payload"
            host_relay.send_answer(client_id, dummy_answer)

            # 等待 Client 接收到 Answer
            for _ in range(30):
                if received_by_client:
                    break
                time.sleep(0.1)

            self.assertTrue(len(received_by_client) > 0, "Client did not receive answer via MQTT")
            self.assertEqual(received_by_client[0][0], dummy_answer)
            self.assertEqual(received_by_client[0][1], host_id)

        finally:
            client_relay.stop()
            host_relay.stop()

if __name__ == '__main__':
    unittest.main()
