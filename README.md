# 🌌 Albireo

<div align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-blue.svg" alt="Python Version">
  <img src="https://img.shields.io/badge/WebRTC-aiortc-orange.svg" alt="WebRTC">
  <img src="https://img.shields.io/badge/Cryptography-Ed25519-success.svg" alt="Security">
  <img src="https://img.shields.io/badge/Architecture-Decentralized-purple.svg" alt="Architecture">
</div>

<h1 align="center">Albireo P2P Communication Protocol</h1>

<p align="center">
  <b>A serverless, cryptographically secure, and decentralized unified communication engine.</b>
</p>

## 🚀 Overview

**Albireo** is an enterprise-grade Peer-to-Peer (P2P) communication platform that operates entirely without centralized servers. Built upon a custom WebRTC Mesh architecture and secured by Ed25519 cryptography, Albireo provides unbreakable, low-latency audio/video communication, file transfers, and a revolutionary decentralized governance system.

Whether you're building a secure enclave for sensitive communications or experimenting with distributed systems, Albireo provides a resilient, anti-fragile foundation.

---

## 🌟 Core Features

### 🛡️ Unbreakable Cryptographic Identity
- **Ed25519 Keypairs**: Every node operates on a uniquely generated private/public keypair.
- **Zero-Trust Payload Signing**: Every single data packet (chat, file metadata, governance votes) is cryptographically signed. Spoofing or man-in-the-middle tampering is mathematically impossible and instantly dropped by the Core Gateway.

### 🌐 Serverless WebRTC Mesh
- **True Decentralization**: No signaling servers, no TURN/STUN middle-men. Connection is established via manual SDP out-of-band handshakes.
- **Mesh Topology**: Nodes automatically orchestrate and discover each other, forming a resilient mesh network.
- **Zlib + Base64 SDP Compression**: Handshake data is massively compressed to easily fit within chat applications for bootstrapping.

### 🎙️ Unified Media Engine
- **Global Audio Mixer**: Multi-channel raw PCM audio mixing with Jitter buffering and voice-activity detection (VAD).
- **Push-to-Talk (PTT) & Open Mic**: Flexible hardware-bound microphone management.
- **Screen Sharing**: High-framerate, dynamically scaled screen broadcasting to all peers.

### 📜 Decentralized Governance & CRDT
- **Democracy Mode**: Nodes can initiate a cryptographic "Vote Kick" against malicious peers. If 50% consensus is reached, the peer is banished network-wide.
- **Archon Mode (Dictatorship)**: The room creator acts as the absolute authority (capable of kicking, disbanding rooms, and revoking screen share privileges).
- **Automated Succession**: If the Archon disconnects, the network seamlessly transitions power to a designated heir. If no heir exists, a deterministic multi-round election initiates. Ties are resolved via cryptographic hash draws to ensure 100% network consensus without a central server.
- **Immunity & Anti-Spam**: Built-in cooldowns and immunity windows prevent governance flooding and vote spam.

### 📦 Modular Service Architecture
- **Facade Pattern (`CoreAPI`)**: The entire complex networking and cryptographic layer is encapsulated behind a single, elegant `CoreAPI` gateway.
- **Micro-Services**: Chat, File Transfer, Screen Sharing, and Voice Mixing are completely decoupled into distinct plugin-like services.
- **AppRunner (Composition Root)**: Manages lifecycle, async event loops, and dependency injection, seamlessly bridging the CustomTkinter UI with underlying services.

### 💾 Local Persistence & State
- **SQLite Database**: Local state (contacts, cryptographic keys, and chat history) is persisted robustly via `albireo_state.db`.
- **CRDT Foundation**: Network message deduplication and local state resolution serve as a robust foundation for CRDT (Conflict-free Replicated Data Type) synchronization, ensuring consistency across mesh peers.

---

## 🏗️ Architecture

```text
┌─────────────────────────────────────────────────────────────┐
│                       CustomTkinter UI                      │
└──────┬────────────────────────┬──────────────────────┬──────┘
       │                        │                      │
┌──────▼──────┐          ┌──────▼──────┐        ┌──────▼──────┐
│ ChatManager │          │ FileTransfer│        │ GovManager  │
└──────┬──────┘          └──────┬──────┘        └──────┬──────┘
       │                        │                      │
       └────────────────────────┼──────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────┐
│                 CoreAPI (Facade & Gateway)                  │
│  [Message Router] [Deduplication] [Auth Hook] [Media Hook]  │
└──────┬───────────────────────────────────────────────┬──────┘
       │                                               │
┌──────▼────────┐                             ┌────────▼──────┐
│ CryptoManager │                             │  WebRTCEngine │
│   (Ed25519)   │                             │   (aiortc)    │
└───────────────┘                             └───────────────┘
```

---

## 🛠️ Installation & Usage

### 1. Requirements
- **OS**: Windows, macOS, or Linux
- **Python**: 3.10 or higher
- Conda (Recommended for managing binary dependencies like PyAV)

### 2. Setup Environment
```bash
# Clone the repository
git clone https://github.com/your-org/p2p-voice.git
cd p2p-voice

# Create conda environment
conda create -n p2p python=3.10
conda activate p2p

# Install dependencies
pip install customtkinter aiortc pynacl sounddevice numpy pillow av pystray
```

### 3. Launching Albireo
```bash
python main.py
```

### 4. How to Connect
1. **Host a Network**: The first user clicks **"Initialize Node"**. The app generates an encrypted, compressed SDP Offer string.
2. **Out-of-Band Handshake**: Send this string to your peer via any secure channel (Telegram, Signal, Discord).
3. **Join Network**: The peer clicks **"Connect to Node"**, pastes the Offer, and generates an Answer.
4. **Finalize**: The peer sends the Answer back to the Host, who completes the WebRTC handshake. You are now connected in a secure P2P mesh!

---

## 🤝 Contributing

Contributions to the Albireo project are highly encouraged. Due to the strict Facade architecture, adding new decentralized features is incredibly simple.

1. Create a new module inside `services/`.
2. Register a message handler with `CoreAPI`.
3. Use `CoreAPI.broadcast_message()` to distribute your state.

Please ensure all new features pass the cryptographic signature tests before submitting a PR.

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
