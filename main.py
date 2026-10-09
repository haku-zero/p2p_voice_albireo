import sys
import argparse

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Albireo P2P Voice")
    parser.add_argument('--headless', action='store_true', help='Run as a headless SFU server')
    parser.add_argument('--room', type=str, help='Room code to join/host in headless mode')
    args = parser.parse_args()
    
    if args.headless:
        if not args.room:
            print("Error: --room is required in headless mode.")
            sys.exit(1)
        from engine.daemon import DaemonRunner
        daemon = DaemonRunner(args.room)
        daemon.start()
    else:
        import customtkinter as ctk
        from engine.app import AppRunner
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")
        app = AppRunner()
        app.start()
