@app.route("/pledge_submit", methods=["POST"])
def pledge_submit():
    data = request.get_json() or {}
    btc_address      = (data.get("btc_address") or "").strip()
    pledge_text      = (data.get("pledge_text") or "").strip()
    recovery_phrase  = (data.get("recovery_phrase") or "").strip()  # ΝΕΟ

    if not btc_address:
        return jsonify(error="Missing BTC address"), 400

    # === CEX Validation (Phase 1A) ===
    # Prevent direct deposits from CEX hot wallets (MEXC, Binance, Kraken)
    # Personal wallet required for KYC/AML compliance
    try:
        from cex_validator import validate_pledge_source
        is_valid_source, source_message = validate_pledge_source(btc_address)

        if not is_valid_source:
            return jsonify(
                status="rejected",
                reason="cex_direct_not_allowed",
                message=source_message,
                suggestion="Withdraw BTC to personal wallet (MetaMask, Ledger, etc.) first"
            ), 403
    except ImportError:
        # If cex_validator not available, continue (graceful degradation)
        pass

    pledges = load_json(PLEDGE_CHAIN, [])
    exists = next((p for p in pledges if p["btc_address"] == btc_address), None)
    if exists:
        # reuse υπάρχον pledge
        return jsonify(
            status="already_verified",
            thr_address=exists["thr_address"],
            pledge_hash=exists["pledge_hash"],
            pdf_filename=exists.get("pdf_filename", f"pledge_{exists['thr_address']}.pdf"),
        ), 200

    # --- BTC verification ή free mode με whitelist ---
    free_list   = load_json(WHITELIST_FILE, [])
    is_dev_free = btc_address in free_list

    if is_dev_free:
        paid = True
        txns = []
    else:
        txns = get_btc_txns(btc_address, BTC_RECEIVER)
        paid = any(
            tx["to"] == BTC_RECEIVER and tx["amount_btc"] >= MIN_AMOUNT
            for tx in txns
        )

    if not paid:
        return jsonify(
            status="pending",
            message="Waiting for BTC payment",
            txns=txns,
        ), 200

    # ── Δημιουργία THR address + pledge hash ──
    thr_addr = f"THR{int(time.time() * 1000)}"
    phash    = hashlib.sha256((btc_address + pledge_text).encode()).hexdigest()

    # ── Core seed που θα κρυφτεί στο PIC OF THE FIRE ──
    # αυτό ΠΟΤΕ δεν αποθηκεύεται καθαρά στον server, μόνο stego + hash
    send_seed      = secrets.token_hex(16)
    send_seed_hash = hashlib.sha256(send_seed.encode()).hexdigest()

    # Auth hash: SHA256(send_seed:auth) - consistent with server.py validate_effective_auth
    if recovery_phrase:
        auth_string = f"{send_seed}:{recovery_phrase}:auth"
    else:
        auth_string = f"{send_seed}:auth"
    send_secret = send_seed  # The raw seed is what the user stores
    send_auth_hash = hashlib.sha256(auth_string.encode()).hexdigest()

    pledge_entry = {
        "btc_address": btc_address,
        "pledge_text": pledge_text,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "pledge_hash": phash,
        "thr_address": thr_addr,
        "send_seed_hash": send_seed_hash,
        "send_auth_hash": send_auth_hash,
    }

    pledges.append(pledge_entry)
    save_json(PLEDGE_CHAIN, pledges)

    # Ύψος chain για το QR / secure PDF
    chain  = load_json(CHAIN_FILE, [])
    height = len(chain)

    # Δημιουργία secure PDF (AES + QR + stego FIRE image)
    pdf_name = create_secure_pdf_contract(
        btc_address=btc_address,
        pledge_text=pledge_text,
        thr_address=thr_addr,
        pledge_hash=phash,
        height=height,
        send_seed=send_seed,          # 🔥 κρυμμένο στο PIC OF THE FIRE
        output_dir=CONTRACTS_DIR,
    )

    # αποθηκεύουμε και το filename στο pledge
    pledge_entry["pdf_filename"] = pdf_name
    save_json(PLEDGE_CHAIN, pledges)

    return jsonify(
        status="verified",
        thr_address=thr_addr,
        pledge_hash=phash,
        pdf_filename=pdf_name,
        send_secret=send_secret,  # το δίνουμε ΜΙΑ φορά στον client σαν “auth_secret”
    ), 200
