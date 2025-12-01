# secure_pledge_embed.py
#
# Δημιουργεί ασφαλές συμβόλαιο PDF:
# - Κρυπτογράφηση (AES/EAX) του payload (btc, thr, pledge_hash, height, send_seed)
# - QR από το THR address + height
# - Stego-στυλ εικόνα με PIC OF THE FIRE + QR
# - LSB Steganography: Embeds the encrypted payload into the image pixels
# - Random όνομα αρχείου (uuid) ώστε να μην σχετίζεται άμεσα με το THR address

import os
import json
import time
import base64
import uuid
import hashlib

from io import BytesIO

import qrcode
from PIL import Image

# ΠΡΟΣΟΧΗ: με pycryptodomex κάνουμε import από Cryptodome.* (όχι Crypto.*)
from Cryptodome.Cipher import AES
from Cryptodome.Random import get_random_bytes


BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Βασική εικόνα για το "fire" (οποιοδήποτε PNG έχεις στο root)
FIRE_BASE_IMAGE = os.path.join(BASE_DIR, "PIC OF THE /images/Fire.jpg")


def _ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


def _encrypt_payload(passphrase: str, payload: dict) -> str:
    """
    Παίρνουμε ένα dict και το κρυπτογραφούμε με AES/EAX.
    Το key βγαίνει από το passphrase (sha256).
    Επιστρέφουμε ένα base64 string: nonce|tag|ciphertext.
    """
    key = hashlib.sha256(passphrase.encode("utf-8")).digest()
    cipher = AES.new(key, AES.MODE_EAX)
    data = json.dumps(payload).encode("utf-8")
    ciphertext, tag = cipher.encrypt_and_digest(data)

    blob = cipher.nonce + tag + ciphertext
    return base64.b64encode(blob).decode("utf-8")


def _make_qr_image(data: str, box_size: int = 8) -> Image.Image:
    """
    Δημιουργεί QR code ως PIL.Image από οποιοδήποτε string.
    """
    qr = qrcode.QRCode(
        version=2,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=box_size,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    return img.convert("RGB")


def _embed_data_lsb(image: Image.Image, data: str) -> Image.Image:
    """
    Embeds the data string into the LSB of the image pixels.
    Terminates with a null byte.
    """
    # Convert data to bits
    # Add null terminator (8 zeros)
    binary_data = ''.join(format(ord(c), '08b') for c in data) + '00000000'
    
    data_len = len(binary_data)
    pixels = list(image.getdata())
    
    if len(pixels) * 3 < data_len:
        raise ValueError("Image too small to hold data")
        
    new_pixels = []
    data_idx = 0
    
    for pixel in pixels:
        if data_idx >= data_len:
            new_pixels.append(pixel)
            continue
            
        r, g, b = pixel
        
        # Modify R
        if data_idx < data_len:
            r = (r & ~1) | int(binary_data[data_idx])
            data_idx += 1
            
        # Modify G
        if data_idx < data_len:
            g = (g & ~1) | int(binary_data[data_idx])
            data_idx += 1
            
        # Modify B
        if data_idx < data_len:
            b = (b & ~1) | int(binary_data[data_idx])
            data_idx += 1
            
        new_pixels.append((r, g, b))
        
    # Fill the rest
    if len(new_pixels) < len(pixels):
        new_pixels.extend(pixels[len(new_pixels):])
        
    new_img = Image.new(image.mode, image.size)
    new_img.putdata(new_pixels)
    return new_img


def _compose_fire_image(thr_address: str, height: int, send_seed: str) -> Image.Image:
    """
    Δημιουργεί την τελική "stego" εικόνα:
    - Φορτώνει το PIC OF THE /images/Fire.jpg (αν υπάρχει)
    - Φτιάχνει QR από THR address + height
    - Κολλάει το QR πάνω στην fire image (πάνω αριστερά)
    """
    # Προετοιμασία βάσης
    if os.path.exists(FIRE_BASE_IMAGE):
        base_img = Image.open(FIRE_BASE_IMAGE).convert("RGB")
    else:
        # fallback: απλά φτιάχνει μαύρο καρέ, για ασφάλεια
        base_img = Image.new("RGB", (800, 600), color=(0, 0, 0))

    w, h = base_img.size

    qr_data = json.dumps(
        {
            "thr_address": thr_address,
            "height": height,
            "ts": int(time.time()),
            # Δεν βάζουμε ολόκληρο το seed εδώ, μόνο ένα hash κομμάτι
            "seed_hint": hashlib.sha256(send_seed.encode("utf-8")).hexdigest()[:16],
        }
    )
    qr_img = _make_qr_image(qr_data, box_size=6)

    # Κλιμάκωση QR
    qr_w, qr_h = qr_img.size
    max_qr_w = int(w * 0.35)
    if qr_w > max_qr_w:
        ratio = max_qr_w / float(qr_w)
        qr_img = qr_img.resize(
            (max_qr_w, int(qr_h * ratio)),
            resample=Image.Resampling.LANCZOS,
        )
        qr_w, qr_h = qr_img.size

    # Επικόλληση πάνω αριστερά με μικρό margin
    margin = 40
    base_img.paste(qr_img, (margin, margin))

    return base_img


def create_secure_pdf_contract(
    btc_address: str,
    pledge_text: str,
    thr_address: str,
    pledge_hash: str,
    height: int,
    send_seed: str,
    output_dir: str,
    passphrase: str = None
) -> str:
    """
    Κεντρική συνάρτηση που καλεί ο server:

    - btc_address: BTC KYC address του pledge
    - pledge_text: το pledge
    - thr_address: THR address που δίνουμε στον χρήστη
    - pledge_hash: sha256(btc_address + pledge_text)
    - height: τρέχον ύψος chain (για context στο QR)
    - send_seed: μικρό μυστικό "seed" για το send_thr
    - output_dir: φάκελος αποθήκευσης (συνήθως DATA_DIR/contracts)
    - passphrase: Ο κωδικός του χρήστη για κρυπτογράφηση. Αν δεν δοθεί, χρησιμοποιείται το send_seed ως fallback key.

    Επιστρέφει μόνο το pdf_name (π.χ. "pledge_abc123.pdf").
    """

    _ensure_dir(output_dir)
    
    # Use passphrase if provided, else fallback to send_seed (though user should provide one)
    encryption_key_source = passphrase if passphrase else send_seed

    # 1. Φτιάχνουμε το κρυπτογραφημένο payload
    payload = {
        "btc_address": btc_address,
        "thr_address": thr_address,
        "pledge_hash": pledge_hash,
        "height": height,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "send_seed": send_seed,
    }
    encrypted_blob = _encrypt_payload(encryption_key_source, payload)

    # 2. Εικόνα με fire + QR
    fire_img = _compose_fire_image(thr_address, height, send_seed)
    
    # 2b. EMBED the encrypted payload into the image bits (Steganography)
    stego_img = _embed_data_lsb(fire_img, encrypted_blob)

    # Αποθήκευση προσωρινού PNG (για embedding στο PDF)
    img_name = f"fire_{uuid.uuid4().hex}.png"
    img_path = os.path.join(output_dir, img_name)
    stego_img.save(img_path, format="PNG") # Must be PNG to preserve LSBs

    # 3. Δημιουργία PDF με FPDF
    from fpdf import FPDF  # import εδώ ώστε να μην βαραίνει το import module

    pdf_name = f"pledge_{uuid.uuid4().hex}.pdf"
    pdf_path = os.path.join(output_dir, pdf_name)

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    pdf.set_font("Courier", "B", 14)
    pdf.cell(0, 10, "Thronos Chain - Pledge Contract", ln=1)

    pdf.set_font("Courier", "", 11)
    pdf.cell(0, 8, f"Node: CPE_GATEWAY", ln=1)
    pdf.cell(0, 8, f"Time: {payload['timestamp']}", ln=1)
    pdf.ln(4)

    pdf.set_font("Courier", "", 11)
    pdf.cell(0, 8, f"BTC Address (KYC): {btc_address}", ln=1)
    pdf.cell(0, 8, f"THR Address: {thr_address}", ln=1)
    pdf.cell(0, 8, f"Pledge Hash: {pledge_hash}", ln=1)
    pdf.cell(0, 8, f"Chain Height at Pledge: {height}", ln=1)
    pdf.ln(4)

    pdf.set_font("Courier", "B", 11)
    pdf.cell(0, 8, "Pledge:", ln=1)
    pdf.set_font("Courier", "", 11)
    pdf.multi_cell(0, 6, pledge_text or "I pledge to the fire that never dies.")
    pdf.ln(4)

    pdf.set_font("Courier", "B", 11)
    pdf.cell(0, 8, "Encrypted Payload (AES/EAX/base64):", ln=1)
    pdf.set_font("Courier", "", 9)
    # σπάμε τη μεγάλη γραμμή σε κομμάτια
    chunk = 80
    for i in range(0, len(encrypted_blob), chunk):
        pdf.multi_cell(0, 5, encrypted_blob[i : i + chunk])
    pdf.ln(4)
    
    pdf.set_font("Courier", "I", 10)
    pdf.cell(0, 8, "Note: This payload is also hidden inside the image below.", ln=1)
    pdf.ln(2)

    # 4. Εισαγωγή της εικόνας (fire + QR + Stego)
    # Βάζουμε την εικόνα χαμηλά στη σελίδα
    try:
        pdf.image(img_path, x=10, y=None, w=150)
    except Exception:
        # Αν αποτύχει για κάποιο λόγο, απλά συνεχίζουμε χωρίς εικόνα
        pass

    pdf.output(pdf_path)

    # 5. Προαιρετικό: καθάρισε το προσωρινό PNG (κρατάμε μόνο το PDF)
    try:
        os.remove(img_path)
    except OSError:
        pass

    return pdf_name