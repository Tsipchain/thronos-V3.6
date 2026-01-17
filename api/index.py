# api/index.py
# Entry point για Vercel – χρησιμοποιεί το υπάρχον Flask app από το server.py

from server import app  # το Flask app = app

# Δεν βάζουμε app.run() εδώ. Ο Vercel σηκώνει μόνος του το app σαν serverless function.
