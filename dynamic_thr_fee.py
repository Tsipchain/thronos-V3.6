
def calculate_dynamic_fee(thr_price_usd: float, target_usd_fee: float = 0.0015) -> float:
    """
    Υπολογίζει πόσα THR χρειάζονται για να ισούνται με το επιθυμητό USD κόστος συναλλαγής.
    Αν η τιμή του THR αυξάνεται, το fee πέφτει αναλογικά.

    :param thr_price_usd: Τρέχουσα τιμή του THR σε USD.
    :param target_usd_fee: Επιθυμητό κόστος συναλλαγής σε USD.
    :return: Ποσότητα THR που ισούται με το target fee.
    """
    if thr_price_usd <= 0:
        raise ValueError("Η τιμή του THR πρέπει να είναι θετική.")
    return round(target_usd_fee / thr_price_usd, 6)

# Example usage:

if __name__ == "__main__":
    thr_price = float(input("Δώσε την τιμή του THR σε USD: "))
    fee = calculate_dynamic_fee(thr_price)
    print(f"Δυναμικό fee: {fee} THR για συναλλαγή ${0.0015}")
