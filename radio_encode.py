
import wave
import numpy as np

def generate_tone(frequency, duration, framerate=44100, amplitude=32767):
    t = np.linspace(0, duration, int(framerate * duration), endpoint=False)
    waveform = amplitude * np.sin(2 * np.pi * frequency * t)
    return waveform.astype(np.int16)

def encode_binary_to_audio(binary_string, filename="thronos_block.wav"):
    framerate = 44100
    tone_duration = 0.1
    pause_duration = 0.05
    signal = np.array([], dtype=np.int16)
    for bit in binary_string:
        if bit == '1':
            tone = generate_tone(880, tone_duration)
        else:
            tone = generate_tone(440, tone_duration)
        pause = np.zeros(int(framerate * pause_duration), dtype=np.int16)
        signal = np.concatenate((signal, tone, pause))
    with wave.open(filename, 'w') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(framerate)
        wf.writeframes(signal.tobytes())

if __name__ == "__main__":
    sample_data = "THR-01::{\"tx\":\"0xdeadbeef\"}"
    binary_data = ''.join(format(ord(c), '08b') for c in sample_data)
    encode_binary_to_audio(binary_data)
