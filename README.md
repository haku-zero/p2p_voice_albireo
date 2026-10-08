# 🌌 Albireo

<div align="center">
  <p><b>A Hardcore, Serverless P2P Voice & Collaboration Terminal with Cyberpunk Aesthetics.</b></p>
  <p>
    <img src="https://img.shields.io/badge/python-3.9%2B-brightgreen.svg" alt="Python Version">
    <img src="https://img.shields.io/badge/WebRTC-aiortc-orange.svg" alt="WebRTC">
    <img src="https://img.shields.io/badge/UI-CustomTkinter-blueviolet.svg" alt="CustomTkinter">
    <img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License">
  </p>
</div>

---

**Albireo Mesh** is a fully decentralized, pure P2P-based communication terminal built for hardcore users. It operates completely serverless—all data (voice, text, screen sharing, and governance) is transmitted directly between peers via WebRTC with Ed25519 Cryptographic Signatures, ensuring absolute privacy, autonomy, and security.

Recent updates have completely overhauled the architecture, transforming Albireo into an enterprise-grade modular application capable of **Star-Topology Multi-Node** connections, featuring a highly-decoupled EventBus architecture and an advanced Network Governance Engine.

## ✨ Core Features

### 🛡️ Unbreakable P2P Networking
- **Zero-Server Architecture**: WebRTC data channels and media tracks form a star-topology mesh directly between the Host and Clients. No central server stores your data.
- **Ed25519 Cryptography**: Every chat, vote, and command is cryptographically signed using `PyNaCl`. Network spoofing and replay attacks are physically impossible.

### 🎙️ High-Fidelity Audio & Video
- **Dynamic Jitter Buffer**: Custom audio mixer with elastic buffering ensures smooth audio playback even under high network latency.
- **Peer-to-Peer Screen Sharing**: Granular, permission-based screen sharing. No forced takeovers.

### 🏛️ Advanced Network Governance
Albireo isn't just a chat app; it's a micro-society. The network creator chooses the governance model:
- **Democracy Mode**: Peer moderation. Any node can initiate a vote to banish a malicious peer. Requires a >50% majority to execute the banishment.
- **Archon Mode (Dictatorship)**: The Host acts as the absolute "Archon" with instant banish rights.
  - **Heir Succession**: The Archon can designate an Heir. If the Archon disconnects, the Heir ascends seamlessly.
  - **Chaos Election**: If the Archon disconnects without an Heir, the remaining nodes automatically trigger a decentralized election protocol to appoint the new Archon.

### 💻 Cyberpunk UI Experience
- Rendered in a high-performance GUI using `CustomTkinter`.
- Neon-cyberpunk aesthetic (`#020205` deep space, `#00FFFF` cyan, `#FF00FF` magenta) with highly responsive modals, floating toasts, and real-time network graphs.

---

## 🛠️ Architecture

Albireo follows a strict **High Cohesion, Low Coupling** modular design:
- **`utils/events.py`**: Global Singleton `EventBus`. The backbone of the application, decoupling the UI completely from the networking engine.
- **`core/engine.py`**: The WebRTC state machine handling SDP signaling, ICE gathering, and DataChannels.
- **`core/governance.py`**: The decentralized state machine handling the Democracy/Archon logic, syncs state across all connected nodes.
- **`core/crypto.py`**: Local identity generation and payload signing/verification.

---

## 🚀 Getting Started

### Prerequisites
- Python 3.9+
- A working microphone and camera (for screen share).

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/albireo-mesh.git
   cd albireo-mesh
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
   *(Dependencies include `aiortc`, `customtkinter`, `sounddevice`, `PyNaCl`, `numpy`, `av`, `Pillow`, `mss`)*

### Usage

Launch the terminal:
```bash
python main.py
```

1. **Host a Network**: Click "Initialize Node" as Host. The app will generate an SDP Offer. Share this encrypted base64 string with your friends via any secure out-of-band channel.
2. **Join a Network**: Click "Connect to Node", paste the Host's SDP Offer, and generate your Answer. Send it back to the Host.
3. **Communicate**: Once connected, voice chat is instant. Use the chat bar to send messages, or click on a peer's avatar to initiate Governance actions (Vote Kick / Assign Heir).

---

## 🤝 Contributing
Pull requests are welcome. For major architectural changes, please open an issue first to discuss what you would like to change. Ensure all Pub/Sub events adhere to the defined `EventBus` payloads.

## 📄 License
[MIT](https://choosealicense.com/licenses/mit/)
