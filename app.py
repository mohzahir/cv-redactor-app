import streamlit as st
import fitz  # PyMuPDF
import re
import io

# Set up the page appearance
st.set_page_config(page_title="CV Redactor Tool", page_icon="📄")
st.title("CV Contact Redactor")
st.write("Upload a PDF CV to automatically redact emails, phone numbers, and LinkedIn URLs.")

# File uploader widget
uploaded_file = st.file_uploader("Upload candidate CV (PDF only)", type=["pdf"])

if uploaded_file is not None:
    st.info("Processing document...")
    
    try:
        # Read the uploaded PDF file into memory
        pdf_bytes = uploaded_file.read()
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        
        # Regex patterns
        email_pattern = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
        phone_pattern = re.compile(r"\+?\d{1,4}?[-.\s]?\(?\d{1,3}?\)?[-.\s]?\d{1,4}[-.\s]?\d{1,4}[-.\s]?\d{1,9}")
        linkedin_pattern = re.compile(r"linkedin\.com/in/[a-zA-Z0-9_-]+")
        patterns = [email_pattern, phone_pattern, linkedin_pattern]
        
        # Process each page
        for page in doc:
            text = page.get_text("text")
            for pattern in patterns:
                for match in pattern.finditer(text):
                    sensitive_text = match.group()
                    text_instances = page.search_for(sensitive_text)
                    for inst in text_instances:
                        # Draw black box
                        page.add_redact_annot(inst, fill=(0, 0, 0))
            page.apply_redactions()
            
        # Save the redacted PDF to a new memory buffer
        output_buffer = io.BytesIO()
        doc.save(output_buffer, garbage=4, deflate=True)
        doc.close()
        
        st.success("Redaction complete!")
        
        # Create a download button for the new file
        st.download_button(
            label="Download Redacted CV",
            data=output_buffer.getvalue(),
            file_name=f"REDACTED_{uploaded_file.name}",
            mime="application/pdf"
        )
        
    except Exception as e:
        st.error(f"An error occurred: {e}")