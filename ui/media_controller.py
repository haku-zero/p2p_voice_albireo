from utils import config
from ui.store import store

class MediaController:
    """
    Acts as the intermediary between the UI (view) and the Media Hardware services.
    Handles user intent (e.g. changing volume, changing devices) and persists settings.
    """
    def __init__(self, local_mic, playback_mgr, inputs_map, outputs_map):
        self.local_mic = local_mic
        self.playback_mgr = playback_mgr
        self.inputs_map = inputs_map
        self.outputs_map = outputs_map

    def toggle_mic(self):
        new_state = not self.local_mic.muted
        self.local_mic.muted = new_state
        store.dispatch("TOGGLE_MIC", new_state)

    def change_mic_volume(self, value):
        val = float(value)
        self.local_mic.volume = val
        config.save_config("mic_vol", val)

    def change_mic_mode(self, mode):
        config.save_config("mic_mode", mode)
        # When entering PTT, mic should be muted by default.
        is_ptt = "ptt" in mode.lower() or "push" in mode.lower() or "按住" in mode
        self.local_mic.muted = is_ptt
        store.dispatch("TOGGLE_MIC", is_ptt)
        return "ptt" if is_ptt else "open"

    def handle_ptt(self, is_pressed):
        mode = config.load_config().get("mic_mode", "")
        if "ptt" in mode.lower() or "push" in mode.lower() or "按住" in mode:
            self.local_mic.muted = not is_pressed
            store.dispatch("TOGGLE_MIC", not is_pressed)

    def toggle_speaker(self):
        new_state = not self.playback_mgr.muted
        self.playback_mgr.muted = new_state
        store.dispatch("TOGGLE_SPEAKER", new_state)

    def change_speaker_volume(self, value):
        val = float(value)
        self.playback_mgr.volume = val
        config.save_config("speaker_vol", val)

    def change_in_device(self, val):
        idx = self.inputs_map.get(val)
        if idx is not None:
            self.local_mic.change_device(idx)
            config.save_config("in_device", val)
        
    def change_out_device(self, val):
        idx = self.outputs_map.get(val)
        if idx is not None:
            self.playback_mgr.change_device(idx)
            config.save_config("out_device", val)
