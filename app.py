import streamlit as st
import fitz  # PyMuPDF
import re
import io
import zipfile
from docx import Document

# Set up the page appearance
st.set_page_config(page_title="CV Redactor Tool", page_icon="📄")
st.title("Bulk CV Contact Redactor (OCR Enabled)")
st.write("Upload multiple PDF (including scanned images) or Word CVs to automatically redact emails, phone numbers, and LinkedIn URLs.")

# File uploader widget
uploaded_files = st.file_uploader("Upload candidate CVs", type=["pdf", "docx"], accept_multiple_files=True)

if uploaded_files:
    st.info(f"Processing {len(uploaded_files)} document(s)...")
    
    # Compile our regex patterns
    email_pattern = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
    phone_pattern = re.compile(r"\+?\d{1,4}?[-.\s]?\(?\d{1,3}?\)?[-.\s]?\d{1,4}[-.\s]?\d{1,4}[-.\s]?\d{1,9}")
    linkedin_pattern = re.compile(r"linkedin\.com/in/[a-zA-Z0-9_-]+")
    patterns = [email_pattern, phone_pattern, linkedin_pattern]

    try:
        zip_buffer = io.BytesIO()
        
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for uploaded_file in uploaded_files:
                file_ext = uploaded_file.name.split('.')[-1].lower()
                output_buffer = io.BytesIO()
                output_filename = f"REDACTED_{uploaded_file.name}"

                # --- LOGIC FOR PDF FILES ---
                if file_ext == "pdf":
                    pdf_bytes = uploaded_file.read()
                    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
                    
                    for page in doc:
                        # 1. Standard text extraction
                        text = page.get_text("text")
                        tp = None  # TextPage placeholder
                        
                        # 2. OCR Fallback for scanned images
                        # If the page has very little text, it is likely an image
                        if len(text.strip()) < 50:
                            try:
                                # Trigger Tesseract OCR to read the image
                                tp = page.get_textpage_ocr(flags=0, language='eng', dpi=150, full=True)
                                text = tp.extractText()
                            except Exception:
                                st.warning(f"Note: Could not run OCR on a page in {uploaded_file.name}")
                        
                        # 3. Find and Redact
                        for pattern in patterns:
                            for match in pattern.finditer(text):
                                sensitive_text = match.group()
                                
                                # If we used OCR, we must search the generated OCR TextPage
                                if tp:
                                    text_instances = page.search_for(sensitive_text, textpage=tp)
                                else:
                                    text_instances = page.search_for(sensitive_text)
                                    
                                for inst in text_instances:
                                    page.add_redact_annot(inst, fill=(0, 0, 0))
                                    
                        # Apply redactions. 'images=fitz.PDF_REDACT_IMAGE_PIXELS' ensures that the underlying 
                        # image data is physically deleted behind the black box so it cannot be recovered.
                        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_PIXELS) 
                        
                    doc.save(output_buffer, garbage=4, deflate=True)
                    doc.close()

                # --- LOGIC FOR WORD FILES ---
                elif file_ext == "docx":
                    docx_bytes = uploaded_file.read()
                    doc = Document(io.BytesIO(docx_bytes))
                    
                    def replace_text_in_run(run):
                        for pattern in patterns:
                            if pattern.search(run.text):
                                run.text = pattern.sub("[REDACTED]", run.text)

                    for para in doc.paragraphs:
                        for run in para.runs:
                            replace_text_in_run(run)
                            
                    for table in doc.tables:
                        for row in table.rows:
                            for cell in row.cells:
                                for para in cell.paragraphs:
                                    for run in para.runs:
                                        replace_text_in_run(run)
                                        
                    doc.save(output_buffer)

                # Write the finished individual file into the zip archive
                zip_file.writestr(output_filename, output_buffer.getvalue())

        st.success("All documents processed successfully!")
        
        st.download_button(
            label="Download All Redacted CVs (ZIP)",
            data=zip_buffer.getvalue(),
            file_name="Redacted_CVs.zip",
            mime="application/zip"
        )
        
    except Exception as e:
        st.error(f"An error occurred while processing: {e}")
