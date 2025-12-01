from PIL import Image
import json
import hashlib
import base64
from Cryptodome.Cipher import AES

def decode_payload_from_image(image_path, passphrase):
    """
    Reads LSBs from the image to get the encrypted blob,
    then attempts to decrypt it using the passphrase.
    """
    try:
        img = Image.open(image_path).convert("RGB")
        bits = ""
        # Read bits until we find the delimiter or run out
        # We look for a null terminator (8 zeros) to stop reading
        for pixel in img.getdata():
            for color in pixel[:3]:  # Only RGB
                bits += str(color & 1)
        
        bytes_list = [bits[i:i+8] for i in range(0, len(bits), 8)]
        decoded_chars = []
        for byte in bytes_list:
            if byte == "00000000":
                break
            decoded_chars.append(chr(int(byte, 2)))
        
        encrypted_blob_b64 = ''.join(decoded_chars)
        
        if not encrypted_blob_b64:
            print("❌ No hidden data found in image.")
            return None

        # Decrypt
        try:
            # Key derivation must match secure_pledge_embed.py
            # key = sha256(passphrase)
            key = hashlib.sha256(passphrase.encode("utf-8")).digest()
            
            # The blob is base64(nonce + tag + ciphertext)
            blob = base64.b64decode(encrypted_blob_b64)
            
            # AES EAX mode
            nonce = blob[:16]
            tag = blob[16:32]
            ciphertext = blob[32:]
            
            cipher = AES.new(key, AES.MODE_EAX, nonce=nonce)
            data = cipher.decrypt_and_verify(ciphertext, tag)
            
            payload_json = data.decode("utf-8")
            payload = json.loads(payload_json)
            return payload
            
        except ValueError:
            print("❌ Decryption failed. Wrong passphrase or corrupted data.")
            return None
        except Exception as e:
            print(f"❌ Error during decryption: {e}")
            return None

    except Exception as e:
        print(f"❌ Error processing image: {e}")
        return None

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 2:
        result = decode_payload_from_image(sys.argv[1], sys.argv[2])
        if result:
            print(json.dumps(result, indent=2))
        else:
            print("Failed to decode.")
    else:
        print("Usage: python phantom_decode.py <image_path> <passphrase>")