"""
Microphone recorder — captures audio into a numpy array while active.
"""
import threading
import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000   # Whisper expects 16kHz mono
MAX_SECONDS = 600     # 10 minutes — Groq's actual limit is 25MB (~13 min at 16kHz)


class Recorder:
    def __init__(self):
        self._chunks = []
        self._active = False
        self._lock = threading.Lock()
        self._stream = None
        self._auto_stop_timer = None
        self._on_max_reached = None

    def start(self, on_max_reached=None):
        self._on_max_reached = on_max_reached
        self._chunks = []
        self._active = True
        # Auto-stop after MAX_SECONDS to stay within Groq's duration limit
        self._auto_stop_timer = threading.Timer(MAX_SECONDS, self._on_timeout)
        self._auto_stop_timer.daemon = True
        self._auto_stop_timer.start()
        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            callback=self._callback,
            blocksize=1024,
        )
        self._stream.start()

    def _on_timeout(self):
        print(f"[recorder] {MAX_SECONDS}s limit reached — auto-stopping")
        if self._on_max_reached:
            self._on_max_reached()

    def stop(self) -> np.ndarray:
        """Stop recording and return the captured audio as float32 array."""
        import time
        if self._auto_stop_timer:
            self._auto_stop_timer.cancel()
            self._auto_stop_timer = None
        time.sleep(0.4)   # trailing buffer — captures end of sentence after key release
        self._active = False
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        with self._lock:
            if not self._chunks:
                return np.zeros(0, dtype=np.float32)
            return np.concatenate(self._chunks, axis=0).flatten()

    def _callback(self, indata, frames, time_info, status):
        if self._active:
            with self._lock:
                self._chunks.append(indata.copy())
