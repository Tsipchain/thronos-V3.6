
import wave
import numpy as np

def decode_audio_to_binary(wav_path, threshold=0.3):
    with wave.open(wav_path, 'r') as wf:
        framerate = wf.getframerate()
        frames = wf.readframes(wf.getnframes())
        audio = np.frombuffer(frames, dtype=np.int16)
    chunk_size = int(framerate * 0.1)
    binary_string = ""
    for i in range(0, len(audio), chunk_size + int(framerate * 0.05)):
        chunk = audio[i:i+chunk_size]
        if len(chunk) < chunk_size:
            continue
        fft_result = np.fft.fft(chunk)
        freqs = np.fft.fftfreq(len(chunk), d=1/framerate)
        dominant_freq = abs(freqs[np.argmax(np.abs(fft_result))])
        if abs(dominant_freq - 880) < 50:
            binary_string += '1'
        elif abs(dominant_freq - 440) < 50:
            binary_string += '0'
    return binary_string

def binary_to_text(binary_string):
    chars = [binary_string[i:i+8] for i in range(0, len(binary_string), 8)]
    text = ""
    for b in chars:
        if b == "00000000":
            break
        try:
            text += chr(int(b, 2))
        except:
            continue
    return text

if __name__ == "__main__":
    wav_file = "thronos_block.wav"
    binary = decode_audio_to_binary(wav_file)
    decoded_message = binary_to_text(binary)
    print("Decoded:", decoded_message)
