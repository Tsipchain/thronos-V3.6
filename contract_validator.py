import os
import json
import hashlib
import argparse
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import Color
from PyPDF2 import PdfReader
import time

class ContractValidator:
    def __init__(self, contract_path=None, pledge_chain_path=None, ledger_path=None, chain_file_path=None):
        """
        Initialize the contract validator with paths to relevant files
        """
        self.contract_path = contract_path
        self.pledge_chain_path = pledge_chain_path or os.path.join(os.path.dirname(__file__), "pledge_chain.json")
        self.ledger_path = ledger_path or os.path.join(os.path.dirname(__file__), "ledger.json")
        self.chain_file_path = chain_file_path or os.path.join(os.path.dirname(__file__), "phantom_tx_chain.json")
    
    def load_json(self, path):
        """
        Load JSON file, return empty dict if file not found
        """
        try:
            with open(path, "r") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}
    
    def extract_pdf_content(self):
        """
        Extract content from PDF contract
        """
        if not self.contract_path or not os.path.exists(self.contract_path):
            print(f"Error: Contract file not found at {self.contract_path}")
            return None
        
        try:
            # Extract text content from PDF
            pdf = PdfReader(self.contract_path)
            text_content = ""
            for page in pdf.pages:
                text_content += page.extract_text()
            
            # Parse the content to extract key information
            contract_data = {}
            
            # Extract BTC Address
            btc_index = text_content.find("BTC Address:")
            if btc_index > -1:
                btc_text = text_content[btc_index:].split("\n", 2)[1].strip()
                contract_data["btc_address"] = btc_text
            
            # Extract THR Address
            thr_index = text_content.find("Generated THR Address:")
            if thr_index > -1:
                thr_text = text_content[thr_index:].split("\n", 2)[1].strip()
                contract_data["thr_address"] = thr_text
            
            # Extract Verification Hash
            hash_index = text_content.find("Verification Hash:")
            if hash_index > -1:
                hash_text = text_content[hash_index:].split("\n", 1)[0].replace("Verification Hash:", "").strip()
                contract_data["verification_hash"] = hash_text
            
            # Extract Contract ID
            id_index = text_content.find("Contract ID:")
            if id_index > -1:
                id_text = text_content[id_index:].split("\n", 1)[0].replace("Contract ID:", "").strip()
                contract_data["contract_id"] = id_text
            
            # Extract Pledge Text (more complex as it can span multiple lines)
            pledge_index = text_content.find("Pledge Text:")
            thr_index = text_content.find("Generated THR Address:")
            if pledge_index > -1 and thr_index > -1:
                # Get text between "Pledge Text:" and "Generated THR Address:"
                pledge_text = text_content[pledge_index + len("Pledge Text:"):thr_index].strip()
                contract_data["pledge_text"] = pledge_text
            
            return contract_data
        except Exception as e:
            print(f"Error extracting content from PDF: {str(e)}")
            return None
    
    def validate_contract(self):
        """
        Validate the contract against blockchain records
        """
        contract_data = self.extract_pdf_content()
        if not contract_data:
            return False, "Could not extract data from contract"
        
        # Load blockchain data
        pledges = self.load_json(self.pledge_chain_path)
        if isinstance(pledges, dict):
            pledges = pledges.get("pledges", [])
        
        chain = self.load_json(self.chain_file_path)
        
        # Verify BTC and THR addresses exist in pledges
        btc_address = contract_data.get("btc_address")
        thr_address = contract_data.get("thr_address")
        
        if not btc_address or not thr_address:
            return False, "Missing BTC or THR address in contract"
        
        # Find the pledge record
        matching_pledge = None
        for pledge in pledges:
            if isinstance(pledge, dict) and pledge.get("btc_address") == btc_address and pledge.get("thr_address") == thr_address:
                matching_pledge = pledge
                break
        
        # If no matching pledge found, check if address exists in the blockchain
        if not matching_pledge:
            address_in_chain = any(
                block.get("thr_address") == thr_address 
                for block in chain 
                if isinstance(block, dict)
            )
            if not address_in_chain:
                return False, f"No record found for THR address {thr_address} in blockchain or pledge records"
            else:
                return True, f"THR address {thr_address} exists in blockchain but not in pledge records"
        
        # Verify hash matches
        expected_hash = hashlib.sha256((btc_address + thr_address).encode()).hexdigest()
        actual_hash = contract_data.get("verification_hash")
        
        if actual_hash != expected_hash:
            return False, f"Verification hash mismatch. Expected: {expected_hash}, Found: {actual_hash}"
        
        # Check if THR address is active in blockchain
        address_active = any(
            block.get("thr_address") == thr_address 
            for block in chain 
            if isinstance(block, dict)
        )
        
        # Get balance if available
        ledger = self.load_json(self.ledger_path)
        balance = ledger.get(thr_address, 0.0) if isinstance(ledger, dict) else 0.0
        
        # Contract is valid
        result_message = (
            f"Contract validated successfully!\n"
            f"BTC Address: {btc_address}\n"
            f"THR Address: {thr_address}\n"
            f"Pledge Date: {matching_pledge.get('timestamp', 'Unknown')}\n"
            f"THR Address Active: {'Yes' if address_active else 'No'}\n"
            f"Current Balance: {balance} THR"
        )
        
        return True, result_message
    
    def generate_validation_report(self, output_path=None):
        """
        Generate a PDF report of the validation results
        """
        is_valid, message = self.validate_contract()
        
        if not output_path:
            # Generate a default output path
            basename = os.path.basename(self.contract_path) if self.contract_path else "unknown"
            output_path = os.path.join(os.path.dirname(self.contract_path) if self.contract_path else ".", 
                                    f"validation_{basename}")
        
        # Create PDF report
        c = canvas.Canvas(output_path, pagesize=letter)
        width, height = letter
        
        # Set up the document
        c.setTitle("Thronos Contract Validation Report")
        c.setAuthor("Thronos Blockchain")
        
        # Add header
        c.setFont("Helvetica-Bold", 20)
        c.drawString(1*inch, height-1*inch, "THRONOS CONTRACT VALIDATION REPORT")
        
        # Add timestamp
        c.setFont("Helvetica", 10)
        c.drawString(1*inch, height-1.3*inch, f"Generated on: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}")
        
        # Add validation status
        c.setFont("Helvetica-Bold", 14)
        if is_valid:
            c.setFillColorRGB(0, 0.5, 0)  # Green
            c.drawString(1*inch, height-2*inch, "VALIDATION STATUS: VALID")
        else:
            c.setFillColorRGB(0.8, 0, 0)  # Red
            c.drawString(1*inch, height-2*inch, "VALIDATION STATUS: INVALID")
        
        # Reset color
        c.setFillColorRGB(0, 0, 0)  # Black
        
        # Add validation details
        c.setFont("Helvetica-Bold", 12)
        c.drawString(1*inch, height-2.5*inch, "Validation Details:")
        
        # Draw separator line
        c.setStrokeColorRGB(0.8, 0.8, 0.8)
        c.line(1*inch, height-2.6*inch, width-1*inch, height-2.6*inch)
        
        # Add validation message
        c.setFont("Helvetica", 11)
        text_object = c.beginText(1*inch, height-2.9*inch)
        
        # Split the validation message into lines
        for line in message.split("\n"):
            text_object.textLine(line)
        
        c.drawText(text_object)
        
        # Add footer
        c.setFont("Helvetica-Italic", 9)
        c.drawString(1*inch, 1*inch, "This is an automatically generated report by the Thronos Blockchain Contract Validator.")
        c.drawString(1*inch, 0.8*inch, f"Report ID: {hashlib.sha256(str(time.time()).encode()).hexdigest()[:16]}")
        
        c.save()
        
        print(f"Validation report generated: {output_path}")
        return output_path, is_valid

def main():
    parser = argparse.ArgumentParser(description="Validate Thronos blockchain contracts")
    parser.add_argument("contract_path", help="Path to the contract PDF file")
    parser.add_argument("--pledge-chain", help="Path to the pledge chain file", default=None)
    parser.add_argument("--ledger", help="Path to the ledger file", default=None)
    parser.add_argument("--chain", help="Path to the blockchain file", default=None)
    parser.add_argument("--output", help="Path for the validation report output", default=None)
    
    args = parser.parse_args()
    
    validator = ContractValidator(
        contract_path=args.contract_path,
        pledge_chain_path=args.pledge_chain,
        ledger_path=args.ledger,
        chain_file_path=args.chain
    )
    
    report_path, is_valid = validator.generate_validation_report(args.output)
    
    exit_code = 0 if is_valid else 1
    return exit_code

if __name__ == "__main__":
    exit_code = main()
    exit(exit_code)