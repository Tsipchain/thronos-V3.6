from PIL import Image
import json
import hashlib
import base64
import os
import io
from Cryptodome.Cipher import AES


def _extract_largest_image_from_pdf(pdf_path):
    """
    Extract the largest embedded image from a PDF file.
    Returns a PIL Image or None.
    """
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(pdf_path)
        best_img = None
        best_size = 0
        for page in doc:
            for img_info in page.get_images(full=True):
                xref = img_info[0]
                try:
                    base_image = doc.extract_image(xref)
                    img_bytes = base_image["image"]
                    if len(img_bytes) > best_size:
                        best_size = len(img_bytes)
                        best_img = img_bytes
                except Exception:
                    continue
        doc.close()
        if best_img:
            return Image.open(io.BytesIO(best_img)).convert("RGB")
    except Exception as e:
        print(f"PDF image extraction failed: {e}")
    return None


def _decode_lsb(img):
    """
    Read LSB bits from an RGB image and return the decoded base64 blob string.
    Optimized: uses bytearray and stops as soon as null terminator is found.
    """
    pixels = img.getdata()
    current_byte = 0
    bit_count = 0
    result = bytearray()

    for pixel in pixels:
        for color in pixel[:3]:  # R, G, B
            current_byte = (current_byte << 1) | (color & 1)
            bit_count += 1
            if bit_count == 8:
                if current_byte == 0:  # null terminator
                    return result.decode("ascii", errors="ignore")
                result.append(current_byte)
                current_byte = 0
                bit_count = 0

    # No null terminator found, return what we have
    return result.decode("ascii", errors="ignore") if result else ""


def _decrypt_blob(encrypted_blob_b64, passphrase):
    """
    Decrypt an AES/EAX base64 blob using the given passphrase.
    Returns the payload dict or None.
    """
    key = hashlib.sha256(passphrase.encode("utf-8")).digest()
    blob = base64.b64decode(encrypted_blob_b64)

    nonce = blob[:16]
    tag = blob[16:32]
    ciphertext = blob[32:]

    cipher = AES.new(key, AES.MODE_EAX, nonce=nonce)
    data = cipher.decrypt_and_verify(ciphertext, tag)

    payload_json = data.decode("utf-8")
    return json.loads(payload_json)


def decode_payload_from_image(file_path, passphrase):
    """
    Reads LSBs from an image (or extracts the stego image from a PDF)
    then attempts to decrypt using the passphrase.

    Supports: .png, .jpg, .jpeg (direct image), .pdf (extract embedded image first)
    """
    try:
        ext = os.path.splitext(file_path)[1].lower()

        # --- PDF: extract the embedded stego image first ---
        if ext == ".pdf":
            img = _extract_largest_image_from_pdf(file_path)
            if img is None:
                print("No image found in PDF.")
                return None
        else:
            img = Image.open(file_path).convert("RGB")

        # --- Decode LSB data ---
        encrypted_blob_b64 = _decode_lsb(img)

        if not encrypted_blob_b64:
            print("No hidden data found in image.")
            return None

        # --- Decrypt ---
        try:
            return _decrypt_blob(encrypted_blob_b64, passphrase)
        except ValueError:
            print("Decryption failed. Wrong passphrase or corrupted data.")
            return None
        except Exception as e:
            print(f"Error during decryption: {e}")
            return None

    except Exception as e:
        print(f"Error processing file: {e}")
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
        print("Usage: python phantom_decode.py <file_path> <passphrase>")