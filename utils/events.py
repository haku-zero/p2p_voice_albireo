import threading

class EventEmitter:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(EventEmitter, cls).__new__(cls)
                cls._instance.listeners = {}
        return cls._instance

    def on(self, event, callback):
        with self._lock:
            if event not in self.listeners:
                self.listeners[event] = []
            if callback not in self.listeners[event]:
                self.listeners[event].append(callback)

    def off(self, event, callback):
        with self._lock:
            if event in self.listeners and callback in self.listeners[event]:
                self.listeners[event].remove(callback)

    def emit(self, event, *args, **kwargs):
        callbacks = []
        with self._lock:
            if event in self.listeners:
                callbacks = list(self.listeners[event])
                
        for callback in callbacks:
            try:
                callback(*args, **kwargs)
            except Exception as e:
                print(f"[EventBus] Error in handler for '{event}': {e}")

event_bus = EventEmitter()
