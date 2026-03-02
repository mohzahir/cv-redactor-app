import streamlit as st
import fitz  # PyMuPDF
import re
import io
import zipfile
import pandas as pd
from docx import Document

st.set_page_config(page_title="Bulk CV Redactor", page_icon="📄")
st.title("Bulk CV Contact Redactor")
st.write("Upload CVs to automatically redact contact info using strict pattern matching, and generate an Excel summary. (No API limits!)")

uploaded_files = st.file_uploader("Upload candidate CVs", type=["pdf", "docx"], accept_multiple_files=True)

if uploaded_files:
    st.info(f"Processing {len(uploaded_files)} document(s)...")
    
    # --- THE UPGRADED STRICT REGEX PATTERNS ---
    email_pattern = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
    # This new phone pattern ignores dates and short IDs
    phone_pattern = re.compile(r"(?<!\d)(?:(?:\+|00)\d{1,3}[\s\-.]?|0\d{1,2}[\s\-.]?)[\d\s\-]{6,10}\d(?!\d)")
    linkedin_pattern = re.compile(r"linkedin\.com/in/[a-zA-Z0-9_-]+")
    
    patterns = [email_pattern, phone_pattern, linkedin_pattern]
    all_candidates_data = []

    try:
        zip_buffer = io.BytesIO()
        
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for uploaded_file in uploaded_files:
                file_ext = uploaded_file.name.split('.')[-1].lower()
                output_buffer = io.BytesIO()
                output_filename = f"REDACTED_{uploaded_file.name}"
                full_text_for_extraction = ""

                # ==========================================
                # PDF PROCESSING
                # ==========================================
                if file_ext == "pdf":
                    pdf_bytes = uploaded_file.read()
                    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
                    
                    for page in doc:
                        text = page.get_text("text")
                        tp = None
                        
                        # OCR Fallback for scanned images
                        if len(text.strip()) < 50:
                            try:
                                tp = page.get_textpage_ocr(flags=0, language='eng', dpi=150, full=True)
                                text = tp.extractText()
                            except Exception:
                                pass
                                
                        full_text_for_extraction += text + "\n"
                        
                        # Apply strict redactions
                        for pattern in patterns:
                            for match in pattern.finditer(text):
                                sensitive_text = match.group()
                                text_instances = page.search_for(sensitive_text, textpage=tp) if tp else page.search_for(sensitive_text)
                                for inst in text_instances:
                                    page.add_redact_annot(inst, fill=(0, 0, 0))
                        
                        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_PIXELS)
                        
                    doc.save(output_buffer, garbage=4, deflate=True)
                    doc.close()

                # ==========================================
                # WORD DOCUMENT PROCESSING
                # ==========================================
                elif file_ext == "docx":
                    docx_bytes = uploaded_file.read()
                    doc_docx = Document(io.BytesIO(docx_bytes))
                    
                    full_text_for_extraction = "\n".join([para.text for para in doc_docx.paragraphs])
                    
                    def replace_text_in_run(run):
                        for pattern in patterns:
                            if pattern.search(run.text):
                                run.text = pattern.sub("[REDACTED]", run.text)

                    for para in doc_docx.paragraphs:
                        for run in para.runs:
                            replace_text_in_run(run)
                            
                    for table in doc_docx.tables:
                        for row in table.rows:
                            for cell in row.cells:
                                for para in cell.paragraphs:
                                    for run in para.runs:
                                        replace_text_in_run(run)
                                        
                    doc_docx.save(output_buffer)

                # ==========================================
                # EXCEL DATA EXTRACTION
                # ==========================================
                found_emails = email_pattern.findall(full_text_for_extraction)
                found_phones = phone_pattern.findall(full_text_for_extraction)
                
                # Guess the name (usually the first non-empty line)
                text_lines = [line.strip() for line in full_text_for_extraction.split('\n') if line.strip()]
                guessed_name = text_lines[0] if text_lines else "Review Manually"

                all_candidates_data.append({
                    "File Name": uploaded_file.name,
                    "Name": guessed_name,
                    "Qualification": "",
                    "Age": "",
                    "Email": found_emails[0] if found_emails else "Not Found",
                    "Phone": found_phones[0] if found_phones else "Not Found",
                    "Current Position": "",
                    "Nationality": "",
                    "Current Location": ""
                })

                zip_file.writestr(output_filename, output_buffer.getvalue())

            # ==========================================
            # GENERATE EXCEL AND ZIP
            # ==========================================
            df = pd.DataFrame(all_candidates_data)
            excel_buffer = io.BytesIO()
            with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name='Candidates')
            
            zip_file.writestr("Candidate_Summary_Data.xlsx", excel_buffer.getvalue())

        st.success("All documents processed successfully! Zero API limits hit.")
        
        st.download_button(
            label="Download Zip (Redacted CVs + Excel Data)",
            data=zip_buffer.getvalue(),
            file_name="Strict_Regex_Processed_CVs.zip",
            mime="application/zip"
        )
        
    except Exception as e:
        st.error(f"An error occurred while processing: {e}")
        
