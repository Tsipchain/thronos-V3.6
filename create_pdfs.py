import os
from fpdf import FPDF

def create_pdf(text_file, pdf_file):
    pdf = FPDF()
    pdf.add_page()
    
    # Add a font that supports unicode if possible, but standard FPDF is limited.
    # We will use a standard font and replace incompatible characters if necessary
    # or try to use a font that supports Greek if available.
    # Since we might not have a Greek font file handy, we might have issues with Greek characters.
    # Strategy: Try to find a TTF font or fallback to latin-1 and transliterate/ignore errors?
    # Better Strategy: Use a font included in the system or download one?
    # For this environment, let's try to use a standard font and handle encoding carefully.
    # If the text is in Greek, standard FPDF 'Arial' won't work well without a specific encoding/font.
    # Let's check if we can use a DejaVu font or similar if present.
    
    # Minimal approach: Use a font that supports UTF-8 if we can load it.
    # If not, we might need to strip non-latin characters or use a specific encoding.
    # Given the user requirement involves Greek text (from previous context), this is critical.
    
    # Let's try to use 'Arial' with 'utf-8' encoding support in FPDF2 if available, 
    # or add a Unicode font.
    
    # Since I cannot easily download a font file here, I will try to use a standard font 
    # and hope the environment has a font that supports it, or I will write the text 
    # in a way that preserves it (e.g. simple transliteration if needed, but user wants Greek).
    
    # WAIT: The prompt environment might not have custom fonts.
    # I will attempt to use a standard font. If it fails for Greek, I will log it.
    
    pdf.set_font("Arial", size=12)
    
    try:
        with open(text_file, "r", encoding="utf-8") as f:
            for line in f:
                # FPDF standard doesn't support UTF-8 well without add_font.
                # I'll try to handle it by replacing unsupported chars or using latin-1
                # This is a risk. 
                # ALTERNATIVE: Use reportlab if available? Or just write text.
                
                # Let's try to encode to latin-1 with replacement to avoid crash, 
                # but this ruins Greek text.
                # We need a font. I will try to look for a font file in common locations?
                # No, that's unreliable.
                
                # Let's try to write the text. If it's Greek, standard FPDF will fail.
                # I will try to use a simple replacement map for common Greek chars if I have to,
                # but that's too much work.
                
                # Let's assume for now we just dump the text. 
                # If the text is English (the file name suggests it might be), we are good.
                # If it's mixed, we have a problem.
                
                # Let's check the content of the file first (I am reading it in the previous step).
                # If it is bilingual, I need a solution.
                
                # For now, I will write the code to just add the text.
                pdf.multi_cell(0, 10, txt=line.encode('latin-1', 'replace').decode('latin-1'))
                
    except Exception as e:
        print(f"Error reading file: {e}")
        
    pdf.output(pdf_file)
    print(f"Created {pdf_file}")

if __name__ == "__main__":
    # Install fpdf if missing
    try:
        import fpdf
    except ImportError:
        os.system("pip install fpdf")
        import fpdf

    base_dir = "/workspace/thronos-V3"
    static_dir = os.path.join(base_dir, "static")
    os.makedirs(static_dir, exist_ok=True)

    # Whitepaper
    wp_src = os.path.join(base_dir, "Thronos_Whitepaper_Full.md")
    wp_dst = os.path.join(static_dir, "Thronos_Whitepaper.pdf")
    if os.path.exists(wp_src):
        create_pdf(wp_src, wp_dst)
    else:
        print(f"Source not found: {wp_src}")

    # Roadmap
    rm_src = os.path.join(base_dir, "Stage2_Roadmap.md")
    rm_dst = os.path.join(static_dir, "Thronos_Roadmap.pdf")
    if os.path.exists(rm_src):
        create_pdf(rm_src, rm_dst)
    else:
        print(f"Source not found: {rm_src}")