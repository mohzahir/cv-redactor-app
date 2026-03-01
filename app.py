import streamlit as st
import fitz  # PyMuPDF
import re
import io
from docx import Document

# Set up the page appearance
st.set_page_config(page_title="CV Redactor Tool", page_icon="📄")
st.title("CV Contact Redactor")
st.write("Upload a PDF or Word CV to automatically redact emails, phone numbers, and LinkedIn URLs.")

# File uploader widget now accepts both pdf and docx
uploaded_file = st.file_uploader("Upload candidate CV", type=["pdf", "docx"])

if uploaded_file is not None:
    st.info("Processing document...")
    
    # Determine the file type
    file_ext = uploaded_file.name.split('.')[-1].lower()
    
    # Compile our regex patterns
    email_pattern = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
    phone_pattern = re.compile(r"\+?\d{1,4}?[-.\s]?\(?\d{1,3}?\)?[-.\s]?\d{1,4}[-.\s]?\d{1,4}[-.\s]?\d{1,9}")
    linkedin_pattern = re.compile(r"linkedin\.com/in/[a-zA-Z0-9_-]+")
    patterns = [email_pattern, phone_pattern, linkedin_pattern]

    try:
        output_buffer = io.BytesIO()

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
            mime_type = "application/pdf"
            output_filename = f"REDACTED_{uploaded_file.name}"

        # --- LOGIC FOR WORD FILES ---
        elif file_ext == "docx":
            doc = Document(uploaded_file)
            
            # Helper function to replace text using regex
            def replace_text_in_run(run):
                for pattern in patterns:
                    if pattern.search(run.text):
                        run.text = pattern.sub("[REDACTED]", run.text)

            # 1. Search regular paragraphs
            for para in doc.paragraphs:
                for run in para.runs:
                    replace_text_in_run(run)
                    
            # 2. Search inside tables (crucial for CV layouts)
            for table in doc.tables:
                for row in table.rows:
                    for cell in row.cells:
                        for para in cell.paragraphs:
                            for run in para.runs:
                                replace_text_in_run(run)
                                
            doc.save(output_buffer)
            mime_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            output_filename = f"REDACTED_{uploaded_file.name}"

        st.success("Redaction complete!")
        
        # Create a download button for the new file
        st.download_button(
            label=f"Download Redacted {file_ext.upper()}",
            data=output_buffer.getvalue(),
            file_name=output_filename,
            mime=mime_type
        )
        
    except Exception as e:
        st.error(f"An error occurred: {e}")
