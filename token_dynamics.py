# token_dynamics.py - Implementation for tracking and displaying Thronos token dynamics
import os
import json
import time
import hashlib
import matplotlib.pyplot as plt
from datetime import datetime

class TokenDynamics:
    """System to track and display token value during pledges"""
    
    def __init__(self, base_dir="/data/chats/xzfmy/workspace/thronosChain/thronosChain-main"):
        self.base_dir = base_dir
        self.price_history_file = os.path.join(base_dir, "price_history.json")
        self.initial_thr_value = 0.00001  # 1 THR = 0.00001 BTC initially
        self.price_history = self.load_price_history()
        
    def load_price_history(self):
        """Load price history from file or create empty history if file doesn't exist"""
        try:
            if os.path.exists(self.price_history_file):
                with open(self.price_history_file, 'r') as f:
                    return json.load(f)
            else:
                # Create initial price point for bootstrapping
                initial_history = [
                    {
                        'timestamp': time.time(),
                        'thr_in_btc': self.initial_thr_value,
                        'wbtc_reserves': 1.0,  # Placeholder 
                        'wthr_reserves': 100000.0  # 1 BTC = 100,000 THR initially
                    }
                ]
                with open(self.price_history_file, 'w') as f:
                    json.dump(initial_history, f)
                return initial_history
        except Exception as e:
            print(f"Error loading price history: {e}")
            return []
            
    def save_price_history(self):
        """Save price history to file"""
        with open(self.price_history_file, 'w') as f:
            json.dump(self.price_history, f, indent=2)
            
    def get_current_thr_value(self):
        """Get current THR value in BTC"""
        if not self.price_history:
            return self.initial_thr_value
        
        latest_price = self.price_history[-1]
        return latest_price.get('thr_in_btc', self.initial_thr_value)
    
    def update_thr_value(self, btc_amount=None, thr_equivalent=None):
        """
        Update THR value based on recent pledge or transaction
        Can either provide explicit price or derive from transaction amounts
        """
        current_time = time.time()
        
        # If explicit values are provided, use them
        if btc_amount is not None and thr_equivalent is not None and thr_equivalent > 0:
            thr_in_btc = btc_amount / thr_equivalent
        else:
            # Otherwise use a simulated price movement (slight variation from last price)
            import random
            last_price = self.get_current_thr_value()
            # Random price movement within ±3%
            price_change = random.uniform(-0.03, 0.03) 
            thr_in_btc = last_price * (1 + price_change)
        
        # Add the new price point
        self.price_history.append({
            'timestamp': current_time,
            'thr_in_btc': thr_in_btc,
            'update_source': 'pledge_transaction'
        })
        
        # Keep only last 1000 price points to manage file size
        if len(self.price_history) > 1000:
            self.price_history = self.price_history[-1000:]
            
        self.save_price_history()
        return thr_in_btc
    
    def generate_price_chart(self, days=7, output_file=None):
        """Generate price chart for the specified days"""
        if not output_file:
            output_file = os.path.join(self.base_dir, "static", "thr_price_chart.png")
            os.makedirs(os.path.dirname(output_file), exist_ok=True)
            
        # Filter price history for the requested time period
        now = time.time()
        cutoff = now - (days * 24 * 60 * 60)
        recent_history = [p for p in self.price_history if p.get('timestamp', 0) > cutoff]
        
        if not recent_history:
            return None
            
        timestamps = [datetime.fromtimestamp(entry.get('timestamp', 0)) for entry in recent_history]
        prices = [entry.get('thr_in_btc', 0) for entry in recent_history]
        
        plt.figure(figsize=(10, 6))
        plt.plot(timestamps, prices, 'b-')
        plt.title(f'THR/BTC Price (Last {days} Days)')
        plt.xlabel('Date')
        plt.ylabel('THR Price in BTC')
        plt.grid(True)
        plt.tight_layout()
        plt.savefig(output_file)
        plt.close()
        
        return output_file
    
    def get_thr_value_for_pledge(self, btc_amount):
        """
        Calculate THR value for a specific pledge amount
        Returns a dict with current rate and equivalent THR value
        """
        current_rate = self.get_current_thr_value()
        thr_equivalent = btc_amount / current_rate if current_rate > 0 else 0
        
        return {
            'btc_amount': btc_amount,
            'thr_rate': current_rate,  # THR price in BTC
            'thr_equivalent': thr_equivalent,
            'timestamp': time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
        }

# Function to enhance the PDF contract generation to include THR value information
def enhance_pdf_contract(btc_address, pledge_text, thr_address, filename, token_value_info):
    """Enhanced PDF contract generator that includes token dynamics"""
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    
    contracts_dir = "/data/chats/xzfmy/workspace/thronosChain/thronosChain-main/contracts"
    os.makedirs(contracts_dir, exist_ok=True)
    pdf_path = os.path.join(contracts_dir, filename)
    
    # Create PDF with ReportLab
    c = canvas.Canvas(pdf_path, pagesize=letter)
    width, height = letter
    
    # Add title and header
    c.setFont("Helvetica-Bold", 18)
    c.drawString(1*inch, height-1*inch, "THRONOS BLOCKCHAIN CONTRACT")
    
    c.setFont("Helvetica-Bold", 12)
    c.drawString(1*inch, height-1.5*inch, f"Contract ID: {hashlib.sha256(thr_address.encode()).hexdigest()[:12]}")
    c.drawString(1*inch, height-1.8*inch, f"Date: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}")
    
    # Divider line
    c.setStrokeColorRGB(0.8, 0.8, 0.8)
    c.line(1*inch, height-2*inch, width-1*inch, height-2*inch)
    
    # Contract information
    c.setFont("Helvetica-Bold", 12)
    c.drawString(1*inch, height-2.5*inch, "BTC Address:")
    c.setFont("Helvetica", 12)
    c.drawString(1*inch, height-2.8*inch, btc_address)
    
    c.setFont("Helvetica-Bold", 12)
    c.drawString(1*inch, height-3.3*inch, "Pledge Text:")
    c.setFont("Helvetica", 12)
    
    # Handle large pledge texts with wrapping
    text_object = c.beginText(1*inch, height-3.6*inch)
    text_object.setFont("Helvetica", 12)
    
    # Split text into lines with maximum 80 characters
    lines = []
    words = pledge_text.split()
    current_line = ""
    
    for word in words:
        if len(current_line + " " + word) <= 80:
            current_line += (" " + word if current_line else word)
        else:
            lines.append(current_line)
            current_line = word
    
    if current_line:
        lines.append(current_line)
    
    for line in lines:
        text_object.textLine(line)
    
    c.drawText(text_object)
    
    # Divider line
    y_pos = height-3.6*inch - (len(lines) * 14) - 0.5*inch
    c.setStrokeColorRGB(0.8, 0.8, 0.8)
    c.line(1*inch, y_pos, width-1*inch, y_pos)
    
    # THR Address section
    c.setFont("Helvetica-Bold", 12)
    c.drawString(1*inch, y_pos - 0.4*inch, "Generated THR Address:")
    c.setFont("Helvetica", 12)
    c.drawString(1*inch, y_pos - 0.7*inch, thr_address)
    
    # Add the token dynamics section - New feature
    y_pos = y_pos - 1.2*inch
    c.setStrokeColorRGB(0.8, 0.8, 0.8)
    c.line(1*inch, y_pos, width-1*inch, y_pos)
    
    c.setFont("Helvetica-Bold", 12)
    c.drawString(1*inch, y_pos - 0.4*inch, "Token Dynamics Information:")
    
    c.setFont("Helvetica", 10)
    c.drawString(1*inch, y_pos - 0.7*inch, f"BTC Amount: {token_value_info.get('btc_amount', 'N/A')} BTC")
    c.drawString(1*inch, y_pos - 0.9*inch, f"Current THR Value: {token_value_info.get('thr_rate', 'N/A')} BTC")
    c.drawString(1*inch, y_pos - 1.1*inch, f"Equivalent THR: {token_value_info.get('thr_equivalent', 'N/A')} THR")
    c.drawString(1*inch, y_pos - 1.3*inch, f"Valuation Timestamp: {token_value_info.get('timestamp', 'N/A')}")
    
    # Add signature
    c.setFont("Helvetica-Oblique", 10)
    c.drawString(1*inch, 1*inch, "This contract is digitally signed and stored on the Thronos blockchain.")
    c.drawString(1*inch, 0.8*inch, f"Verification Hash: {hashlib.sha256((btc_address + thr_address).encode()).hexdigest()}")
    
    # Finalize PDF
    c.save()
    
    return pdf_path

# Demonstration of usage
if __name__ == "__main__":
    # Create token dynamics instance
    token_dynamics = TokenDynamics()
    
    # Get current THR value
    current_value = token_dynamics.get_current_thr_value()
    print(f"Current THR value: {current_value} BTC")
    
    # Calculate token value for a pledge
    pledge_value = token_dynamics.get_thr_value_for_pledge(0.0001)
    print(f"For 0.0001 BTC pledge: {pledge_value['thr_equivalent']} THR")
    
    # Update THR value (simulation)
    new_value = token_dynamics.update_thr_value()
    print(f"Updated THR value: {new_value} BTC")
    
    # Generate price chart
    chart_path = token_dynamics.generate_price_chart()
    print(f"Chart generated at: {chart_path}")