import streamlit as st
import fitz  # PyMuPDF
import re
import io
import zipfile
from docx import Document

# Set up the page appearance
st.set_page_config(page_title="CV Redactor Tool", page_icon="📄")
st.title("Bulk CV Contact Redactor")
st.write("Upload multiple PDF or Word CVs to automatically redact emails, phone numbers, and LinkedIn URLs.")

# File uploader widget now accepts MULTIPLE files
uploaded_files = st.file_uploader("Upload candidate CVs", type=["pdf", "docx"], accept_multiple_files=True)

if uploaded_files:
    st.info(f"Processing {len(uploaded_files)} document(s)...")
    
    # Compile our regex patterns
    email_pattern = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
    phone_pattern = re.compile(r"\+?\d{1,4}?[-.\s]?\(?\d{1,3}?\)?[-.\s]?\d{1,4}[-.\s]?\d{1,4}[-.\s]?\d{1,9}")
    linkedin_pattern = re.compile(r"linkedin\.com/in/[a-zA-Z0-9_-]+")
    patterns = [email_pattern, phone_pattern, linkedin_pattern]

    try:
        # Create an in-memory zip file to hold all redacted CVs
        zip_buffer = io.BytesIO()
        
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            # Loop through every file you uploaded
            for uploaded_file in uploaded_files:
                file_ext = uploaded_file.name.split('.')[-1].lower()
                output_buffer = io.BytesIO()
                output_filename = f"REDACTED_{uploaded_file.name}"

                # --- LOGIC FOR PDF FILES ---
                if file_ext == "pdf":
                    pdf_bytes = uploaded_file.read()
                    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
                    
                    for page in doc:
                        text = page.get_text("text")
                        for pattern in patterns:
                            for match in pattern.finditer(text):
                                sensitive_text = match.group()
                                text_instances = page.search_for(sensitive_text)
                                for inst in text_instances:
                                    page.add_redact_annot(inst, fill=(0, 0, 0))
                        page.apply_redactions()
                        
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

                    # Search paragraphs
                    for para in doc.paragraphs:
                        for run in para.runs:
                            replace_text_in_run(run)
                            
                    # Search tables
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
        
        # Create a single download button for the whole Zip folder
        st.download_button(
            label="Download All Redacted CVs (ZIP)",
            data=zip_buffer.getvalue(),
            file_name="Redacted_CVs.zip",
            mime="application/zip"
        )
        
    except Exception as e:
        st.error(f"An error occurred while processing: {e}")
