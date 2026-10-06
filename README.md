# 🌌 Albireo

**A Pure P2P, Serverless Voice & File Transfer Terminal with Cyberpunk Aesthetics.**

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.8%2B-brightgreen.svg)
![WebRTC](https://img.shields.io/badge/WebRTC-aiortc-orange.svg)

Albireo is a fully decentralized, pure P2P-based communication terminal designed for LAN and WAN environments. It operates completely serverless—all data (voice, text, and files) is transmitted directly between two peers via WebRTC with End-to-End Encryption (E2EE), ensuring absolute privacy and security.

---

## 🌟 Features

- **🛡️ 100% Serverless**: No registration, no central servers, and no third-party signaling relays. Connections are established through a hardcore, manual Base64 token handshake for absolute isolation.
- **🎙️ Low-Latency Audio Engine**: Deeply integrates `aiortc` and `pyaudio` (native WASAPI drivers) to completely eliminate network blocking and audio stuttering commonly found in traditional multi-threaded environments. Supports Open Mic and Push-to-Talk (PTT).
- **⚡ Gigabit File Streaming**: Built-in dynamic backpressure flow control for WebRTC DataChannels. Achieves uncapped, gigabit speeds on local networks while maintaining absolute stability and preventing buffer overflows on weak internet connections. Features a dynamic cyberpunk progress bar.
- **💬 Secure Chat**: Built-in encrypted CLI-style chat room inside the UI.
- **🎨 Cyberpunk Deep Void Aesthetics**: A handcrafted deep space UI built with `customtkinter`, featuring neon borders, hover glows, and strict monospace typography.
- **🌐 Dynamic i18n**: Seamless hot-swapping between English and Chinese, with all text heavily localized to fit a hardcore tech/hacker aesthetic.

---

## 🛠️ Installation

### 1. Requirements
Ensure you have **Python 3.8 or higher** installed on your system.

### 2. Clone the Repository
```bash
git clone https://github.com/haku-zero/p2p_voice_albireo.git
cd p2p_voice_albireo
```

### 3. Install Dependencies
```bash
pip install customtkinter pyaudio aiortc av pystray Pillow numpy
```
*(Note: If you encounter compilation errors installing `pyaudio` on Windows, please use a precompiled `.whl` file or install via `pipwin install pyaudio`)*

### 4. Launch the Terminal
```bash
python main.py
```

---

## 🎮 How to Connect

Since Albireo is a pure P2P architecture, the first connection requires a manual "Handshake Token" exchange via any third-party app (Discord, Telegram, WeChat, etc.).

1. **Host Node**
   - Click `[ INITIALIZE_HOST_NODE ]`.
   - Wait for the Client to send you their Offer Token.

2. **Client Node**
   - Click `[ CONNECT_TO_REMOTE_NODE ]`.
   - Click `[ GENERATE_UPLINK_OFFER ]` and send the generated token to the Host.

3. **Handshake Phase**
   - **Host**: Paste the received Offer Token into Phase 1 and click `[ COMPUTE_AUTHORIZATION_ANSWER ]`. Send the generated **Answer Token** back to the Client.
   - **Client**: Paste the Answer Token into Phase 2 and click `[ FINALIZE_UPLINK ]`.
   - **Done**: The secure P2P link is now established. You can immediately use voice chat, send secure messages, and transfer files!

---

## 📁 Architecture Overview
- `main.py`: Central Mediator. Manages the asyncio event loop and dispatches callbacks.
- `webrtc.py`: Pure networking layer. Handles Offer/Answer SDP exchange, ICE traversal, and the dynamic file data pump.
- `audio.py`: Hardware driver layer. Uses asynchronous queue mechanisms to bridge PyAudio and aiortc media tracks.
- `ui.py`: Visual presentation layer. Stripped of all blocking logic, acting purely as a UI component container.
- `i18n.py`: Internationalization dictionary engine.

---

## 📜 License
This project is open-sourced under the [MIT License](LICENSE). You are free to use, modify, and distribute it, but please retain the original author information.
