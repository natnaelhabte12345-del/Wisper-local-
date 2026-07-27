"""
Mikrofon-Diagnose für WisprWin.

    .venv\\Scripts\\python.exe tools\\mic_check.py

Misst Grundrauschen und Sprachpegel und sagt, ob das Mikrofon für Whisper
laut genug ist. Wichtig ist nicht die absolute Lautstärke, sondern der
Abstand zwischen Sprache und Rauschen (SNR).
"""
import os
import sys
import time

import numpy as np
import sounddevice as sd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SR = 16000


def rms(a: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(a)))) if a.size else 0.0


def record(seconds: float) -> np.ndarray:
    buf = sd.rec(int(seconds * SR), samplerate=SR, channels=1, dtype="float32")
    for left in range(int(seconds), 0, -1):
        print(f"   {left}...", end="\r", flush=True)
        time.sleep(1)
    sd.wait()
    print("        ", end="\r")
    return buf.flatten()


def main() -> None:
    dev = sd.query_devices(kind="input")
    print(f"Eingabegerät: {dev['name']}\n")

    print("1/2  STILL SEIN (3 Sekunden) — messe Grundrauschen")
    input("     Enter zum Start...")
    noise = record(3)
    noise_rms = rms(noise)
    print(f"     Rauschen: {noise_rms:.4f}\n")

    print("2/2  NORMAL SPRECHEN (5 Sekunden), so laut wie beim Diktieren")
    input("     Enter zum Start...")
    speech = record(5)

    # Nur die lauten Frames zählen — Pausen zwischen Wörtern verfälschen sonst
    frames = speech[: speech.size // 320 * 320].reshape(-1, 320)
    frame_rms = np.sqrt(np.mean(np.square(frames), axis=1))
    voiced = frame_rms[frame_rms > max(noise_rms * 2, 0.002)]
    speech_rms = float(np.mean(voiced)) if voiced.size else 0.0
    peak = float(np.max(np.abs(speech)))
    clipped = int(np.sum(np.abs(speech) > 0.99))

    print(f"     Sprache:  {speech_rms:.4f}")
    print(f"     Spitze:   {peak:.3f}")
    print(f"     Sprachanteil: {voiced.size / max(len(frame_rms), 1):.0%}\n")

    print("─" * 52)
    snr = 20 * np.log10(speech_rms / noise_rms) if noise_rms > 0 and speech_rms > 0 else 0
    print(f"SNR: {snr:.1f} dB")

    ok = True
    if speech_rms < 0.005:
        print("PROBLEM  Mikrofon zu leise für zuverlässige Erkennung. In Windows unter")
        print("         Sound > Eingabe den Pegel anheben oder Mikrofonverstärkung an.")
        ok = False
    elif speech_rms < 0.02:
        print("KNAPP    Leise, aber über der Verwerfungsschwelle. Pegel anheben lohnt sich,")
        print("         ist aber vermutlich nicht die Ursache von Transkriptionsfehlern.")
    else:
        print("OK       Pegel gut.")

    if noise_rms < 0.0002:
        print("HINWEIS  Grundrauschen praktisch null — das Mikrofon hat ein Noise Gate.")
        print("         Der SNR-Wert unten ist dadurch geschönt und wenig aussagekräftig.")

    if snr and snr < 20:
        print("PROBLEM  Zu wenig Abstand zum Rauschen. Näher ans Mikro oder")
        print("         Störquelle (Lüfter, Fenster) abstellen.")
        ok = False
    elif snr:
        print(f"OK       Rauschabstand ausreichend ({snr:.0f} dB).")

    if clipped > 100:
        print(f"PROBLEM  {clipped} übersteuerte Samples — Pegel zu hoch, runterdrehen.")
        ok = False

    print()
    # Single source of truth — sonst meldet das Tool eine Schwelle, die nicht mehr gilt.
    from transcriber import _MIN_RMS
    print(f"Zum Vergleich: WisprWin verwirft alles unter rms={_MIN_RMS} als Stille.")
    if speech_rms:
        print(f"Dein Sprachpegel liegt {speech_rms / _MIN_RMS:.0f}x darüber.")
    print()
    print("FAZIT: Mikrofon ist nicht die Fehlerquelle." if ok
          else "FAZIT: Hier liegt vermutlich ein echtes Problem — siehe oben.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
