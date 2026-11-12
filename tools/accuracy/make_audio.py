"""Synthesize the corpus with many TTS voices, then degrade it like Nati's real mic chain.

    PYTHONPATH=<dir with edge_tts> .venv\\Scripts\\python.exe tools\\accuracy\\make_audio.py <out_dir>

Writes <out_dir>/audio/<id>.wav (16 kHz mono, what WisprWin sends) + manifest.json.
His real clips sit around -33..-38 dBFS RMS, so that is the default level here.
"""
import asyncio
import json
import os
import random
import subprocess
import sys

import numpy as np
import scipy.io.wavfile as wavio
import scipy.signal as sig

sys.path.insert(0, os.path.dirname(__file__))
import edge_tts  # noqa: E402
from corpus import PASSAGES  # noqa: E402

EN_VOICES = [
    "en-US-AvaNeural", "en-US-AndrewNeural", "en-US-BrianNeural", "en-US-EmmaNeural",
    "en-US-GuyNeural", "en-US-JennyNeural", "en-US-ChristopherNeural", "en-US-EricNeural",
    "en-GB-LibbyNeural", "en-GB-RyanNeural", "en-GB-SoniaNeural", "en-GB-ThomasNeural",
    "en-AU-NatashaNeural", "en-AU-WilliamMultilingualNeural", "en-IN-NeerjaNeural",
    "en-IN-PrabhatNeural", "en-IE-ConnorNeural", "en-IE-EmilyNeural", "en-ZA-LeahNeural",
    "en-ZA-LukeNeural", "en-NG-AbeoNeural", "en-NG-EzinneNeural", "en-KE-ChilembaNeural",
    "en-PH-JamesNeural", "en-SG-WayneNeural", "en-CA-LiamNeural", "en-NZ-MollyNeural",
]
DE_VOICES = ["de-DE-KatjaNeural", "de-DE-ConradNeural", "de-DE-AmalaNeural", "de-DE-KillianNeural",
             "de-AT-IngridNeural", "de-AT-JonasNeural", "de-CH-JanNeural", "de-CH-LeniNeural"]
# German voices reading English text = a German speaker's accent, as a stress test.
ACCENT_VOICES = ["de-DE-ConradNeural", "de-DE-KatjaNeural", "de-DE-KillianNeural",
                 "de-AT-JonasNeural", "de-DE-AmalaNeural"]

# name: (rate, level dBFS, snr dB or None, bandpass, reverb)
CONDS = {
    "mic34":     ("+0%", -34, 30, False, False),
    "headset":   ("+0%", -36, 18, True, False),
    "noisy":     ("+0%", -33, 10, False, True),
    "fast":      ("+25%", -34, 22, False, False),
    "accent_de": ("+0%", -34, 30, False, False),
    "clean20":   ("+0%", -20, None, False, False),
    "mumble":    ("+15%", -38, 15, True, False),
}
EN_ORDER = ["mic34", "headset", "noisy", "fast", "accent_de", "clean20", "mumble"]


def pink_noise(n, rng):
    spec = np.fft.rfft(rng.standard_normal(n))
    f = np.arange(spec.size, dtype=float)
    f[0] = 1
    x = np.fft.irfft(spec / np.sqrt(f), n)
    return x / np.sqrt(np.mean(x ** 2))


def rms_db(x):
    return 20 * np.log10(np.sqrt(np.mean(x ** 2)) + 1e-12)


def degrade(x, rate_cond, rng):
    _, level, snr, band, reverb = rate_cond
    if band:
        b, a = sig.butter(4, [250, 3800], btype="band", fs=16000)
        x = sig.lfilter(b, a, x)
    if reverb:
        n = int(0.45 * 16000)
        ir = rng.standard_normal(n) * np.exp(-np.arange(n) / (0.09 * 16000))
        wet = sig.fftconvolve(x, ir / np.sqrt(np.sum(ir ** 2)))[: x.size]
        x = 0.6 * x + 0.5 * wet
    if snr is not None:
        sp = np.sqrt(np.mean(x ** 2))
        x = x + pink_noise(x.size, rng) * sp / (10 ** (snr / 20))
    x = x * 10 ** ((level - rms_db(x)) / 20)
    return np.clip(x, -1, 1).astype(np.float32)


async def synth(text, voice, rate, mp3, sem):
    async with sem:
        for attempt in range(4):
            try:
                await edge_tts.Communicate(text, voice, rate=rate).save(mp3)
                return
            except Exception as e:  # network hiccup / throttling
                if attempt == 3:
                    raise
                await asyncio.sleep(2 + attempt * 3)


async def main(out):
    os.makedirs(os.path.join(out, "audio"), exist_ok=True)
    rng = np.random.default_rng(11)
    random.seed(11)
    sem = asyncio.Semaphore(3)
    jobs, manifest = [], []
    ei = 0
    for p in PASSAGES:
        if p["lang"] == "de":
            cond = "mic34" if len(manifest) % 2 else "headset"
            voice = DE_VOICES[len(manifest) % len(DE_VOICES)]
        else:
            cond = EN_ORDER[ei % len(EN_ORDER)]
            if p.get("long") and cond in ("accent_de", "clean20"):
                cond = "mic34"
            voice = (ACCENT_VOICES[ei % len(ACCENT_VOICES)] if cond == "accent_de"
                     else EN_VOICES[(ei * 5 + 2) % len(EN_VOICES)])
            ei += 1
        mp3 = os.path.join(out, "audio", p["id"] + ".mp3")
        manifest.append({**p, "cond": cond, "voice": voice, "mp3": mp3,
                         "wav": os.path.join(out, "audio", p["id"] + ".wav")})
        jobs.append(synth(p["text"], voice, CONDS[cond][0], mp3, sem))
    await asyncio.gather(*jobs)

    ffmpeg = os.environ.get("FFMPEG", "ffmpeg")
    for m in manifest:
        raw = m["mp3"].replace(".mp3", "_raw.wav")
        subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", m["mp3"], "-ac", "1",
                        "-ar", "16000", raw], check=True)
        sr, x = wavio.read(raw)
        x = x.astype(np.float32) / 32768
        # Real recordings carry ~0.4 s of room before and after the speech.
        pad = np.zeros(int(0.4 * 16000), np.float32)
        x = degrade(np.concatenate([pad, x, pad]), CONDS[m["cond"]], rng)
        wavio.write(m["wav"], 16000, (x * 32767).astype(np.int16))
        m["seconds"] = round(x.size / 16000, 1)
        m["dbfs"] = round(float(rms_db(x)), 1)
        os.remove(raw)
    json.dump(manifest, open(os.path.join(out, "manifest.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    tot = sum(m["seconds"] for m in manifest)
    print(f"{len(manifest)} clips, {tot:.0f}s audio, {len({m['voice'] for m in manifest})} voices")
    from collections import Counter
    print(Counter(m["cond"] for m in manifest))


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
