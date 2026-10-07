# 🌌 Albireo

<div align="center">
  <p><b>A Hardcore, Serverless P2P Voice & File Transfer Terminal with Cyberpunk Aesthetics.</b></p>
  <p>
    <img src="https://img.shields.io/badge/python-3.9%2B-brightgreen.svg" alt="Python Version">
    <img src="https://img.shields.io/badge/WebRTC-aiortc-orange.svg" alt="WebRTC">
    <img src="https://img.shields.io/badge/UI-CustomTkinter-blueviolet.svg" alt="CustomTkinter">
    <img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License">
  </p>
</div>

---

**Albireo** is a fully decentralized, pure P2P-based communication terminal designed for hardcore users. It operates completely serverless—all data (voice, text, and files) is transmitted directly between peers via WebRTC with End-to-End Encryption (E2EE), ensuring absolute privacy and security.

Recent updates have completely overhauled the architecture, transforming Albireo into an enterprise-grade modular application capable of **Star-Topology Multi-Node** connections (SFU/MCU architecture), featuring a custom elastic jitter buffer and concurrent file multiplexing.

---

## ✨ Key Features

### 🎙️ Extreme P2P Audio Engine (`CustomMixerTrack`)
- **Serverless Star Topology**: The Host node acts as a lightweight SFU (Selective Forwarding Unit) and MCU (Multipoint Control Unit), routing and mixing audio for all connected clients.
- **60ms Elastic Jitter Buffer**: Custom NumPy-based audio frame buffering algorithm completely eliminates audio tearing and stuttering caused by network fluctuations.
- **Hardware Integration**: Native PyAudio integration with Push-to-Talk (PTT) and Open Mic modes.

### ⚡ Concurrent Multiplexed File Transfers
- **UUID-Prefixed Data Chunks**: Say goodbye to blocking transfers. Albireo utilizes a custom multiplexing protocol over WebRTC DataChannels, allowing **multiple files and text messages to be transmitted simultaneously in both directions**.
- **In-Chat Rendering**: Real-time Cyberpunk progress bars and instant, in-place image rendering for `.jpg`/`.png` files upon transfer completion.

### 🏗️ Highly Decoupled Architecture (DDD & MVC)
- The codebase has been surgically refactored for High Cohesion and Low Coupling:
  - **`core/`**: Deep business logic, entirely stripped of UI dependencies. Contains the WebRTC Engine, Audio Mixer, and virtual `AppRunner`.
  - **`ui/`**: Pure visual presentation layer utilizing `customtkinter`.
  - **`utils/`**: Configuration and i18n dictionaries.

### 🎨 Deep Void Cyberpunk Aesthetics
- Handcrafted deep space UI built with `customtkinter`.
- Neon borders, hover glows, and strict monospace typography (`Consolas`).
- Seamless hot-swapping between English and Chinese (`i18n`).

---

## 🛠️ Installation

### 1. Requirements
Ensure you have **Python 3.9 or higher** installed on your system.

### 2. Clone the Repository
```bash
git clone https://github.com/your-username/albireo-p2p.git
cd albireo-p2p
```

### 3. Install Dependencies
```bash
pip install customtkinter pyaudio aiortc av pystray Pillow numpy
```
*(Note: If you encounter compilation errors installing `pyaudio` on Windows, you can install the precompiled binary using `pip install pipwin` followed by `pipwin install pyaudio`)*

### 4. Launch the Terminal
```bash
python main.py
```

---

## 🎮 How to Connect

Since Albireo is a pure P2P application, establishing a connection requires a manual "Handshake Token" (SDP Base64) exchange via any third-party secure channel (e.g., Signal, Telegram).

1. **Host Node**
   - Click `[ INITIALIZE_HOST_NODE ]`.
   - You will enter the room as the Host. Wait for Clients to send you their Offer Tokens.

2. **Client Node**
   - Click `[ CONNECT_TO_REMOTE_NODE ]`.
   - Click `[ GENERATE_UPLINK_OFFER ]` to generate your Offer Token. Copy and send it to the Host.

3. **Handshake Phase**
   - **Host**: Clicks the `[ GENERATE_INVITE_TOKEN ]` wizard, pastes the Client's Offer Token into Phase 1, and clicks `[ COMPUTE_AUTHORIZATION_ANSWER ]`. Sends the generated **Answer Token** back to the Client.
   - **Client**: Pastes the Host's Answer Token into Phase 2 and clicks `[ FINALIZE_UPLINK ]`.
   - **Done**: The secure P2P link is established! The topology list will update, and you can immediately begin transmitting voice and files.

---

## 📁 Architecture Overview

```text
p2p-voice/
│
├── main.py                 # Pure Entry Point
├── core/                   # Deep Engine Layer
│   ├── runner.py           # Virtual Executor (App Lifecycle & State Machine)
│   ├── engine.py           # WebRTC Call Control & DataChannel Orchestration
│   ├── audio_io.py         # PyAudio Hardware I/O Bridging
│   ├── audio_mixer.py      # CustomMixerTrack (60ms Jitter Buffer & NumPy Mixing)
│   └── file_transfer.py    # UUID Concurrent File Chunking Protocol
│
├── ui/                     # View Layer (CustomTkinter)
│   ├── ui_manager.py       # Main UI Controller & Top Bar
│   ├── chat_view.py        # Chat bubbles & File progress bars
│   ├── member_view.py      # Topology, Ping, and Voice Activity Indicators (VAD)
│   ├── modals.py           # Host/Client Signaling Wizards
│   └── theme.py            # Cyberpunk Color & Font Constants
│
└── utils/                  # Shared Utilities
    ├── config.py           # settings.json I/O persistence
    └── i18n.py             # Internationalization dictionaries
```

---

## 🧪 Automated Integration Tests

Albireo includes a hardcore, headless integration test suite that simulates multi-node networking in memory.

```bash
# Run tests from the project root:
python -m test.test_multinode
```

This suite spins up 1 Host and 2 Clients simultaneously, verifying:
- Star-Topology multi-way handshake stability.
- Prevention of Chat Relay infinite loops (Relay Guards).
- Proper UUID multiplexing during file transfers.
- Jitter buffer under-run and over-run constraints.

---

## 📜 License
This project is open-sourced under the [MIT License](LICENSE). 
You are free to use, modify, and distribute it, provided you retain the original author information.
