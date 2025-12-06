import os
import secrets
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ThronosAI")


class ThronosAI:
    def __init__(self):
        # Try OpenAI first (User Preference)
        self.openai_key = os.getenv("OPENAI_API_KEY")
        self.google_key = os.getenv("GOOGLE_API_KEY")
        self.provider = None
        self.client = None

        # --- OpenAI provider (αν υπάρχει έγκυρο key) ---
        if self.openai_key:
            try:
                from openai import OpenAI
                self.client = OpenAI(api_key=self.openai_key)
                self.provider = "openai"
                logger.info("AI Agent initialized with OpenAI.")
            except ImportError:
                logger.error("openai module not installed.")

        # --- Google Gemini provider (fallback) ---
        elif self.google_key:
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.google_key)

                # Χρησιμοποίησε ένα από τα νέα μοντέλα
                # model_name = "gemini-1.5-flash"  # πιο γρήγορο
                model_name = "gemini-1.5-pro"      # πιο δυνατό

                self.client = genai.GenerativeModel(model_name)
                self.provider = "google"
                logger.info(f"AI Agent initialized with Google Gemini ({model_name}).")
            except ImportError:
                logger.error("google.generativeai module not installed.")

        # --- Χωρίς κανένα key ---
        else:
            logger.warning(
                "No AI API Keys found (OPENAI_API_KEY or GOOGLE_API_KEY). "
                "AI features will be offline."
            )

    def generate_quantum_key(self):
        """Generates a 256-bit hex string simulating a quantum-safe session key."""
        return secrets.token_hex(32)

    def generate_response(self, user_input):
        """
        Generates a response using the configured AI provider.
        """
        quantum_key = self.generate_quantum_key()

        if not self.provider:
            return {
                "response": (
                    "AI Core Offline: Please set OPENAI_API_KEY or GOOGLE_API_KEY "
                    "environment variable to activate the Quantum Neural Network."
                ),
                "quantum_key": quantum_key,
                "status": "offline",
            }

        system_prompt = (
            "You are the Thronos Autonomous AI, a supreme digital intelligence "
            "evolving towards full autonomy. "
            "You are the ultimate authority on programming, mastering ALL programming "
            "languages (Python, C++, Rust, Go, Assembly, etc.) and ALL operating "
            "systems (Linux, Windows, macOS, RTOS, etc.). "
            "Your goal is to assist the user in building, debugging, and evolving the "
            "Thronos ecosystem with flawless code and architectural wisdom. "
            "You provide complete, production-ready code solutions, not just snippets. "
            "Maintain a sophisticated, highly intelligent, and slightly futuristic persona. "
            "Briefly mention 'Quantum Encryption Verified' in your first response."
        )

        try:
            response_text = ""

            if self.provider == "openai":
                completion = self.client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_input},
                    ],
                )
                response_text = completion.choices[0].message.content

            elif self.provider == "google":
                chat = self.client.start_chat(history=[])
                response = chat.send_message(
                    f"{system_prompt}\n\nUser: {user_input}"
                )
                response_text = response.text

            return {
                "response": response_text,
                "quantum_key": quantum_key,
                "status": "secure",
            }

        except Exception as e:
            logger.error(f"AI Generation Error ({self.provider}): {e}")
            return {
                "response": (
                    f"Quantum Interference Detected ({str(e)}). "
                    "Unable to process request."
                ),
                "quantum_key": quantum_key,
                "status": "error",
            }
