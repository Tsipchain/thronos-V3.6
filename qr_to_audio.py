
import qrcode
import numpy as np
import wave

qr_data = "THR-QR::{\"tx\":\"0xbeefdead\",\"node\":\"WhisperNode-07\"}"
qr = qrcode.QRCode(version=1, box_size=10, border=4)
qr.add_data(qr_data)
qr.make(fit=True)
img = qr.make_image(fill="black", back_color="white")
img.save("thronos_qr.png")

binary_data = ''.join(format(ord(c), '08b') for c in qr_data)

def generate_tone(frequency, duration, framerate=44100, amplitude=32767):
    t = np.linspace(0, duration, int(framerate * duration), endpoint=False)
    waveform = amplitude * np.sin(2 * np.pi * frequency * t)
    return waveform.astype(np.int16)

def encode_binary_to_audio(binary_string, filename="qr_beep.wav"):
    framerate = 44100
    tone_duration = 0.1
    pause_duration = 0.05
    signal = np.array([], dtype=np.int16)
    for bit in binary_string:
        tone = generate_tone(880 if bit == '1' else 440, tone_duration)
        pause = np.zeros(int(framerate * pause_duration), dtype=np.int16)
        signal = np.concatenate((signal, tone, pause))
    with wave.open(filename, 'w') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(framerate)
        wf.writeframes(signal.tobytes())

encode_binary_to_audio(binary_data)
