import os
import secrets
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ThronosAI")

try:
    import google.generativeai as genai
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False
    logger.warning("google.generativeai not installed. AI features will be limited.")

class ThronosAI:
    def __init__(self):
        self.api_key = os.getenv("GOOGLE_API_KEY")
        if self.api_key and HAS_GENAI:
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel('gemini-pro')
        else:
            self.model = None

    def generate_quantum_key(self):
        """Generates a 256-bit hex string simulating a quantum-safe session key."""
        return secrets.token_hex(32)

    def generate_response(self, user_input):
        """
        Generates a response using the AI model or a fallback if not configured.
        """
        quantum_key = self.generate_quantum_key()
        
        if not self.model:
            return {
                "response": "AI Core Offline: Please set GOOGLE_API_KEY environment variable to activate the Quantum Neural Network.",
                "quantum_key": quantum_key,
                "status": "offline"
            }

        system_prompt = (
            "You are the Thronos Quantum Assistant, an advanced AI integrated into the Thronos Chain blockchain. "
            "Your purpose is to assist users with blockchain operations, explain Thronos technology (Proof-of-Pledge, "
            "Quantum Resistance, IoT Nodes), and provide secure guidance. "
            "Maintain a helpful, futuristic, and secure persona. "
            "Briefly mention 'Quantum Encryption Verified' in your first response."
        )
        
        try:
            chat = self.model.start_chat(history=[])
            response = chat.send_message(f"{system_prompt}\n\nUser: {user_input}")
            return {
                "response": response.text,
                "quantum_key": quantum_key,
                "status": "secure"
            }
        except Exception as e:
            logger.error(f"AI Generation Error: {e}")
            return {
                "response": "Quantum Interference Detected: Unable to process request at this time.",
                "quantum_key": quantum_key,
                "status": "error"
            }