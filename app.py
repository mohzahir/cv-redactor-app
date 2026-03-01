import streamlit as st
import fitz  # PyMuPDF
import re
import io
import zipfile
import pandas as pd
from docx import Document

st.set_page_config(page_title="CV Redactor & Extractor", page_icon="📄")
st.title("Bulk CV Redactor & Data Extractor")
st.write("Upload CVs to redact contact info AND generate an Excel summary of candidate data.")

uploaded_files = st.file_uploader("Upload candidate CVs", type=["pdf", "docx"], accept_multiple_files=True)

if uploaded_files:
    st.info(f"Processing {len(uploaded_files)} document(s)...")
    
    email_pattern = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
    phone_pattern = re.compile(r"(?<!\w)(?:(?:\+|00)\d{1,3}[-.\s]?|(?:\(?0\d{1,2}\)?)[-.\s]?)(?:\d[-.\s]?){6,10}\b")
    linkedin_pattern = re.compile(r"linkedin\.com/in/[a-zA-Z0-9_-]+")
    patterns = [email_pattern, phone_pattern, linkedin_pattern]

    # This list will hold all the data for our Excel sheet
    all_candidates_data = []

    try:
        zip_buffer = io.BytesIO()
        
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for uploaded_file in uploaded_files:
                file_ext = uploaded_file.name.split('.')[-1].lower()
                output_buffer = io.BytesIO()
                output_filename = f"REDACTED_{uploaded_file.name}"
                
                full_text_for_extraction = ""

                # --- LOGIC FOR PDF FILES ---
                if file_ext == "pdf":
                    pdf_bytes = uploaded_file.read()
                    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
                    
                    for page in doc:
                        text = page.get_text("text")
                        tp = None
                        
                        if len(text.strip()) < 50:
                            try:
                                tp = page.get_textpage_ocr(flags=0, language='eng', dpi=150, full=True)
                                text = tp.extractText()
                            except Exception:
                                pass
                                
                        full_text_for_extraction += text + "\n"
                        
                        # Redaction process
                        for pattern in patterns:
                            for match in pattern.finditer(text):
                                sensitive_text = match.group()
                                text_instances = page.search_for(sensitive_text, textpage=tp) if tp else page.search_for(sensitive_text)
                                for inst in text_instances:
                                    page.add_redact_annot(inst, fill=(0, 0, 0))
                        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_PIXELS)
                        
                    doc.save(output_buffer, garbage=4, deflate=True)
                    doc.close()

                # --- LOGIC FOR WORD FILES ---
                elif file_ext == "docx":
                    docx_bytes = uploaded_file.read()
                    doc = Document(io.BytesIO(docx_bytes))
                    
                    # Extract text for our Excel sheet before redacting
                    full_text_for_extraction = "\n".join([para.text for para in doc.paragraphs])
                    
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

                # --- DATA EXTRACTION FOR EXCEL ---
                # Find all emails and phones in the raw text
                found_emails = email_pattern.findall(full_text_for_extraction)
                found_phones = phone_pattern.findall(full_text_for_extraction)
                
                # Guess the name (usually the first non-empty line of a CV)
                text_lines = [line.strip() for line in full_text_for_extraction.split('\n') if line.strip()]
                guessed_name = text_lines[0] if text_lines else "Unknown"

                # Append to our master list
                all_candidates_data.append({
                    "File Name": uploaded_file.name,
                    "Candidate Name (Guessed)": guessed_name,
                    "Email": found_emails[0] if found_emails else "Not Found",
                    "Phone": found_phones[0] if found_phones else "Not Found",
                    "Qualification": "",
                    "Age": "",
                    "Current Position": "",
                    "Nationality": "",
                    "Current Location": ""
                })

                # Write redacted CV to zip
                zip_file.writestr(output_filename, output_buffer.getvalue())

            # --- CREATE THE EXCEL FILE ---
            # Convert our list of data into a Pandas DataFrame (a digital table)
            df = pd.DataFrame(all_candidates_data)
            
            # Save the DataFrame to an Excel file in memory
            excel_buffer = io.BytesIO()
            with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name='Candidates')
            
            # Add the completed Excel file into the Zip folder
            zip_file.writestr("Candidate_Summary_Data.xlsx", excel_buffer.getvalue())

        st.success("All documents processed! Excel sheet generated.")
        
        st.download_button(
            label="Download Zip (Redacted CVs + Excel Data)",
            data=zip_buffer.getvalue(),
            file_name="Processed_CVs_and_Data.zip",
            mime="application/zip"
        )
        
    except Exception as e:
        st.error(f"An error occurred while processing: {e}")

