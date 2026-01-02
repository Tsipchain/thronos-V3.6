#!/usr/bin/env python3
"""
Thronos i18n Manager - Multi-Language Support
=============================================
Full internationalization system for 5+ languages

Supported Languages:
- Greek (el) - Ελληνικά
- English (en) - English
- Spanish (es) - Español
- German (de) - Deutsch
- French (fr) - Français
- Japanese (ja) - 日本語
- Chinese (zh) - 中文

Features:
- JSON-based translation files
- Dynamic language switching
- Template integration
- API response localization
- Date/time formatting
- Number/currency formatting
- RTL language support

Phase 4 Enhancement
Version: 3.7
"""

import os
import json
import logging
from typing import Dict, Any, Optional
from pathlib import Path
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class I18nManager:
    """
    Internationalization Manager for Thronos Chain
    """

    # Supported languages with metadata
    LANGUAGES = {
        'el': {
            'name': 'Ελληνικά',
            'name_en': 'Greek',
            'flag': '🇬🇷',
            'rtl': False,
            'date_format': '%d/%m/%Y',
            'time_format': '%H:%M',
            'decimal_separator': ',',
            'thousands_separator': '.'
        },
        'en': {
            'name': 'English',
            'name_en': 'English',
            'flag': '🇬🇧',
            'rtl': False,
            'date_format': '%Y-%m-%d',
            'time_format': '%H:%M',
            'decimal_separator': '.',
            'thousands_separator': ','
        },
        'es': {
            'name': 'Español',
            'name_en': 'Spanish',
            'flag': '🇪🇸',
            'rtl': False,
            'date_format': '%d/%m/%Y',
            'time_format': '%H:%M',
            'decimal_separator': ',',
            'thousands_separator': '.'
        },
        'de': {
            'name': 'Deutsch',
            'name_en': 'German',
            'flag': '🇩🇪',
            'rtl': False,
            'date_format': '%d.%m.%Y',
            'time_format': '%H:%M',
            'decimal_separator': ',',
            'thousands_separator': '.'
        },
        'fr': {
            'name': 'Français',
            'name_en': 'French',
            'flag': '🇫🇷',
            'rtl': False,
            'date_format': '%d/%m/%Y',
            'time_format': '%H:%M',
            'decimal_separator': ',',
            'thousands_separator': ' '
        },
        'ja': {
            'name': '日本語',
            'name_en': 'Japanese',
            'flag': '🇯🇵',
            'rtl': False,
            'date_format': '%Y年%m月%d日',
            'time_format': '%H:%M',
            'decimal_separator': '.',
            'thousands_separator': ','
        },
        'zh': {
            'name': '中文',
            'name_en': 'Chinese',
            'flag': '🇨🇳',
            'rtl': False,
            'date_format': '%Y年%m月%d日',
            'time_format': '%H:%M',
            'decimal_separator': '.',
            'thousands_separator': ','
        }
    }

    def __init__(self, translations_dir: str = "translations", default_lang: str = "el"):
        self.translations_dir = Path(translations_dir)
        self.translations_dir.mkdir(exist_ok=True)
        self.default_lang = default_lang
        self.current_lang = default_lang

        # Load all translations
        self.translations: Dict[str, Dict[str, str]] = {}
        self._load_all_translations()

        # Create default translation files if they don't exist
        self._initialize_translation_files()

        logger.info(f"🌍 i18n Manager initialized with {len(self.translations)} languages")

    def _load_all_translations(self):
        """Load all translation files"""
        for lang_code in self.LANGUAGES.keys():
            lang_file = self.translations_dir / f"{lang_code}.json"
            if lang_file.exists():
                try:
                    with open(lang_file, 'r', encoding='utf-8') as f:
                        self.translations[lang_code] = json.load(f)
                    logger.info(f"Loaded translations for {lang_code}")
                except Exception as e:
                    logger.error(f"Error loading {lang_code} translations: {e}")
                    self.translations[lang_code] = {}
            else:
                self.translations[lang_code] = {}

    def _initialize_translation_files(self):
        """Create default translation files"""
        # Core translations for each language
        default_translations = {
            'el': self._get_greek_translations(),
            'en': self._get_english_translations(),
            'es': self._get_spanish_translations(),
            'de': self._get_german_translations(),
            'fr': self._get_french_translations(),
            'ja': self._get_japanese_translations(),
            'zh': self._get_chinese_translations(),
        }

        for lang_code, translations in default_translations.items():
            lang_file = self.translations_dir / f"{lang_code}.json"
            if not lang_file.exists() or len(self.translations.get(lang_code, {})) == 0:
                try:
                    with open(lang_file, 'w', encoding='utf-8') as f:
                        json.dump(translations, f, indent=2, ensure_ascii=False)
                    self.translations[lang_code] = translations
                    logger.info(f"Created translation file: {lang_code}.json")
                except Exception as e:
                    logger.error(f"Error creating {lang_code} translation file: {e}")

    def _get_greek_translations(self) -> Dict[str, str]:
        """Greek translations"""
        return {
            # Common
            "welcome": "Καλώς ήρθατε",
            "home": "Αρχική",
            "about": "Σχετικά",
            "contact": "Επικοινωνία",
            "login": "Σύνδεση",
            "logout": "Αποσύνδεση",
            "register": "Εγγραφή",
            "submit": "Υποβολή",
            "cancel": "Ακύρωση",
            "confirm": "Επιβεβαίωση",
            "delete": "Διαγραφή",
            "edit": "Επεξεργασία",
            "save": "Αποθήκευση",
            "search": "Αναζήτηση",
            "loading": "Φόρτωση...",
            "error": "Σφάλμα",
            "success": "Επιτυχία",

            # Blockchain
            "blockchain": "Blockchain",
            "wallet": "Πορτοφόλι",
            "balance": "Υπόλοιπο",
            "transaction": "Συναλλαγή",
            "transactions": "Συναλλαγές",
            "block": "Block",
            "blocks": "Blocks",
            "mining": "Mining",
            "hash": "Hash",
            "address": "Διεύθυνση",
            "send": "Αποστολή",
            "receive": "Λήψη",
            "amount": "Ποσό",
            "fee": "Προμήθεια",
            "confirmations": "Επιβεβαιώσεις",

            # DeFi
            "defi": "DeFi",
            "swap": "Ανταλλαγή",
            "liquidity": "Ρευστότητα",
            "pool": "Pool",
            "pools": "Pools",
            "stake": "Stake",
            "unstake": "Unstake",
            "rewards": "Ανταμοιβές",
            "amm": "AMM",
            "dex": "DEX",
            "token": "Token",
            "tokens": "Tokens",
            "price": "Τιμή",
            "volume": "Όγκος",

            # Bridge
            "bridge": "Γέφυρα",
            "deposit": "Κατάθεση",
            "withdraw": "Ανάληψη",
            "wrapped": "Wrapped",

            # AI
            "ai": "AI",
            "chat": "Chat",
            "pythia": "Πυθία",
            "oracle": "Μαντείο",
            "autonomous": "Αυτόνομο",

            # Status
            "pending": "Εκκρεμεί",
            "processing": "Επεξεργασία",
            "completed": "Ολοκληρώθηκε",
            "failed": "Απέτυχε",
            "cancelled": "Ακυρώθηκε",

            # Time
            "today": "Σήμερα",
            "yesterday": "Χθες",
            "week": "Εβδομάδα",
            "month": "Μήνας",
            "year": "Έτος",

            # Messages
            "transaction_sent": "Η συναλλαγή στάλθηκε επιτυχώς",
            "transaction_failed": "Η συναλλαγή απέτυχε",
            "insufficient_balance": "Ανεπαρκές υπόλοιπο",
            "invalid_address": "Μη έγκυρη διεύθυνση",
        }

    def _get_english_translations(self) -> Dict[str, str]:
        """English translations"""
        return {
            # Common
            "welcome": "Welcome",
            "home": "Home",
            "about": "About",
            "contact": "Contact",
            "login": "Login",
            "logout": "Logout",
            "register": "Register",
            "submit": "Submit",
            "cancel": "Cancel",
            "confirm": "Confirm",
            "delete": "Delete",
            "edit": "Edit",
            "save": "Save",
            "search": "Search",
            "loading": "Loading...",
            "error": "Error",
            "success": "Success",

            # Blockchain
            "blockchain": "Blockchain",
            "wallet": "Wallet",
            "balance": "Balance",
            "transaction": "Transaction",
            "transactions": "Transactions",
            "block": "Block",
            "blocks": "Blocks",
            "mining": "Mining",
            "hash": "Hash",
            "address": "Address",
            "send": "Send",
            "receive": "Receive",
            "amount": "Amount",
            "fee": "Fee",
            "confirmations": "Confirmations",

            # DeFi
            "defi": "DeFi",
            "swap": "Swap",
            "liquidity": "Liquidity",
            "pool": "Pool",
            "pools": "Pools",
            "stake": "Stake",
            "unstake": "Unstake",
            "rewards": "Rewards",
            "amm": "AMM",
            "dex": "DEX",
            "token": "Token",
            "tokens": "Tokens",
            "price": "Price",
            "volume": "Volume",

            # Bridge
            "bridge": "Bridge",
            "deposit": "Deposit",
            "withdraw": "Withdraw",
            "wrapped": "Wrapped",

            # AI
            "ai": "AI",
            "chat": "Chat",
            "pythia": "Pythia",
            "oracle": "Oracle",
            "autonomous": "Autonomous",

            # Status
            "pending": "Pending",
            "processing": "Processing",
            "completed": "Completed",
            "failed": "Failed",
            "cancelled": "Cancelled",

            # Time
            "today": "Today",
            "yesterday": "Yesterday",
            "week": "Week",
            "month": "Month",
            "year": "Year",

            # Messages
            "transaction_sent": "Transaction sent successfully",
            "transaction_failed": "Transaction failed",
            "insufficient_balance": "Insufficient balance",
            "invalid_address": "Invalid address",
        }

    def _get_spanish_translations(self) -> Dict[str, str]:
        """Spanish translations"""
        base = self._get_english_translations()
        base.update({
            "welcome": "Bienvenido",
            "home": "Inicio",
            "about": "Acerca de",
            "contact": "Contacto",
            "login": "Iniciar sesión",
            "logout": "Cerrar sesión",
            "register": "Registrarse",
            "wallet": "Cartera",
            "balance": "Saldo",
            "transaction": "Transacción",
            "transactions": "Transacciones",
            "send": "Enviar",
            "receive": "Recibir",
            "amount": "Cantidad",
            "fee": "Tarifa",
            "liquidity": "Liquidez",
            "rewards": "Recompensas",
        })
        return base

    def _get_german_translations(self) -> Dict[str, str]:
        """German translations"""
        base = self._get_english_translations()
        base.update({
            "welcome": "Willkommen",
            "home": "Startseite",
            "about": "Über",
            "contact": "Kontakt",
            "login": "Anmelden",
            "logout": "Abmelden",
            "register": "Registrieren",
            "wallet": "Brieftasche",
            "balance": "Guthaben",
            "transaction": "Transaktion",
            "transactions": "Transaktionen",
            "send": "Senden",
            "receive": "Empfangen",
            "amount": "Betrag",
            "fee": "Gebühr",
        })
        return base

    def _get_french_translations(self) -> Dict[str, str]:
        """French translations"""
        base = self._get_english_translations()
        base.update({
            "welcome": "Bienvenue",
            "home": "Accueil",
            "about": "À propos",
            "contact": "Contact",
            "login": "Connexion",
            "logout": "Déconnexion",
            "register": "S'inscrire",
            "wallet": "Portefeuille",
            "balance": "Solde",
            "transaction": "Transaction",
            "transactions": "Transactions",
            "send": "Envoyer",
            "receive": "Recevoir",
            "amount": "Montant",
            "fee": "Frais",
        })
        return base

    def _get_japanese_translations(self) -> Dict[str, str]:
        """Japanese translations"""
        base = self._get_english_translations()
        base.update({
            "welcome": "ようこそ",
            "home": "ホーム",
            "about": "について",
            "contact": "お問い合わせ",
            "login": "ログイン",
            "logout": "ログアウト",
            "register": "登録",
            "wallet": "ウォレット",
            "balance": "残高",
            "transaction": "トランザクション",
            "transactions": "トランザクション",
            "send": "送信",
            "receive": "受信",
            "amount": "金額",
            "fee": "手数料",
        })
        return base

    def _get_chinese_translations(self) -> Dict[str, str]:
        """Chinese translations"""
        base = self._get_english_translations()
        base.update({
            "welcome": "欢迎",
            "home": "首页",
            "about": "关于",
            "contact": "联系",
            "login": "登录",
            "logout": "登出",
            "register": "注册",
            "wallet": "钱包",
            "balance": "余额",
            "transaction": "交易",
            "transactions": "交易",
            "send": "发送",
            "receive": "接收",
            "amount": "金额",
            "fee": "费用",
        })
        return base

    def set_language(self, lang_code: str) -> bool:
        """Set current language"""
        if lang_code in self.LANGUAGES:
            self.current_lang = lang_code
            logger.info(f"Language set to: {self.LANGUAGES[lang_code]['name']}")
            return True
        return False

    def t(self, key: str, lang: Optional[str] = None, **kwargs) -> str:
        """
        Translate a key to current or specified language

        Args:
            key: Translation key
            lang: Optional language code (uses current_lang if not specified)
            **kwargs: Variables to substitute in translation

        Returns:
            Translated string
        """
        lang_code = lang or self.current_lang

        if lang_code not in self.translations:
            lang_code = self.default_lang

        translation = self.translations[lang_code].get(key, key)

        # Substitute variables
        if kwargs:
            try:
                translation = translation.format(**kwargs)
            except KeyError:
                pass

        return translation

    def get_language_info(self, lang_code: str) -> Optional[Dict[str, Any]]:
        """Get metadata for a language"""
        return self.LANGUAGES.get(lang_code)

    def get_available_languages(self) -> Dict[str, Dict[str, Any]]:
        """Get all available languages"""
        return self.LANGUAGES

    def format_number(self, number: float, lang: Optional[str] = None) -> str:
        """Format number according to language conventions"""
        lang_code = lang or self.current_lang
        info = self.LANGUAGES.get(lang_code, self.LANGUAGES[self.default_lang])

        # Format with proper separators
        decimal_sep = info['decimal_separator']
        thousands_sep = info['thousands_separator']

        # Simple formatting (for production, use locale)
        formatted = f"{number:,.2f}"
        formatted = formatted.replace(',', 'TEMP')
        formatted = formatted.replace('.', decimal_sep)
        formatted = formatted.replace('TEMP', thousands_sep)

        return formatted

    def format_date(self, timestamp: float, lang: Optional[str] = None) -> str:
        """Format date according to language conventions"""
        lang_code = lang or self.current_lang
        info = self.LANGUAGES.get(lang_code, self.LANGUAGES[self.default_lang])

        dt = datetime.fromtimestamp(timestamp)
        return dt.strftime(info['date_format'])

    def format_datetime(self, timestamp: float, lang: Optional[str] = None) -> str:
        """Format datetime according to language conventions"""
        lang_code = lang or self.current_lang
        info = self.LANGUAGES.get(lang_code, self.LANGUAGES[self.default_lang])

        dt = datetime.fromtimestamp(timestamp)
        return f"{dt.strftime(info['date_format'])} {dt.strftime(info['time_format'])}"


# Global instance
i18n = I18nManager()


def main():
    """Test the i18n system"""
    print("🌍 Thronos i18n Manager Test\n")

    manager = I18nManager()

    print("Available languages:")
    for code, info in manager.get_available_languages().items():
        print(f"  {info['flag']} {code}: {info['name']} ({info['name_en']})")

    print("\nTranslation tests:")
    for lang in ['el', 'en', 'es', 'de', 'fr', 'ja', 'zh']:
        welcome = manager.t('welcome', lang=lang)
        print(f"  {lang}: {welcome}")

    print("\nNumber formatting:")
    number = 1234567.89
    for lang in ['el', 'en', 'de', 'fr']:
        formatted = manager.format_number(number, lang)
        print(f"  {lang}: {formatted}")

    print("\nDate formatting:")
    timestamp = time.time()
    for lang in ['el', 'en', 'ja', 'zh']:
        formatted = manager.format_datetime(timestamp, lang)
        print(f"  {lang}: {formatted}")


if __name__ == "__main__":
    import time
    main()
