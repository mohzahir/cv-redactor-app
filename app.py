import streamlit as st
import fitz  # PyMuPDF
import io
import zipfile
import pandas as pd
import json
import time  # <--- NEW: We need this to pause the script
import google.generativeai as genai
from docx import Document

st.set_page_config(page_title="AI CV Redactor & Extractor", page_icon="🤖")
st.title("AI-Powered Bulk CV Redactor")
st.write("Upload CVs to have Google Gemini intelligently find and redact contact info, while generating an Excel summary.")

# Safely load the API Key and force JSON output
try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    model = genai.GenerativeModel(
        'gemini-2.5-flash',
        generation_config={"response_mime_type": "application/json"}
    )
except Exception as e:
    st.error(f"⚠️ API Setup Error: {e}")

uploaded_files = st.file_uploader("Upload candidate CVs", type=["pdf", "docx"], accept_multiple_files=True)

if uploaded_files:
    st.info(f"Processing {len(uploaded_files)} document(s). This will take a moment to prevent rate-limiting...")
    all_candidates_data = []

    try:
        zip_buffer = io.BytesIO()
        
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for uploaded_file in uploaded_files:
                file_ext = uploaded_file.name.split('.')[-1].lower()
                output_buffer = io.BytesIO()
                output_filename = f"REDACTED_{uploaded_file.name}"
                
                doc_text = ""
                doc = None

                # ==========================================
                # PASS 1: EXTRACT ALL TEXT FOR THE AI
                # ==========================================
                file_bytes = uploaded_file.read()
                
                if file_ext == "pdf":
                    doc = fitz.open(stream=file_bytes, filetype="pdf")
                    for page in doc:
                        text = page.get_text("text")
                        if len(text.strip()) < 50:
                            try:
                                text = page.get_textpage_ocr(flags=0, language='eng', dpi=150, full=True).extractText()
                            except Exception:
                                pass
                        doc_text += text + "\n"
                        
                elif file_ext == "docx":
                    doc_docx = Document(io.BytesIO(file_bytes))
                    doc_text = "\n".join([para.text for para in doc_docx.paragraphs])

                # ==========================================
                # PASS 2: AI INTELLIGENCE & JSON EXTRACTION
                # ==========================================
                ai_prompt = f"""
                Extract the candidate's details from the CV text into a JSON object using exactly these keys:
                "Name", "Qualification", "Age", "Email", "Phone", "Current Position", "Nationality", "Current Location".
                If a piece of information is missing, use "Not Found" as the value.

                CRITICAL INSTRUCTION FOR REDACTION:
                Create a 9th key named "Exact_Contacts_To_Redact". This must be an array of strings containing EVERY phone number, email address, and LinkedIn profile URL you found in the text.
                You MUST extract these strings EXACTLY as they appear in the text, character-for-character, including all spaces, dashes, or formatting.
                
                CV Text:
                {doc_text[:8000]}
                """
                
                try:
                    response = model.generate_content(ai_prompt)
                    extracted_data = json.loads(response.text)
                    
                    # --- THE FIX ---
                    # Tell Python to wait 4 seconds before the next API call to avoid 429 Quota errors
                    time.sleep(4) 
                    
                except Exception as e:
                    error_msg = f"System Error: {str(e)[:40]}"
                    extracted_data = {
                        "Name": error_msg, "Qualification": error_msg, "Age": error_msg, 
                        "Email": error_msg, "Phone": error_msg, "Current Position": error_msg, 
                        "Nationality": error_msg, "Current Location": error_msg,
                        "Exact_Contacts_To_Redact": []
                    }

                strings_to_redact = extracted_data.get("Exact_Contacts_To_Redact", [])
                
                candidate_record = {"File Name": uploaded_file.name}
                for key in ["Name", "Qualification", "Age", "Email", "Phone", "Current Position", "Nationality", "Current Location"]:
                    candidate_record[key] = extracted_data.get(key, "Not Found")
                all_candidates_data.append(candidate_record)

                # ==========================================
                # PASS 3: REDACT THE EXACT STRINGS
                # ==========================================
                if file_ext == "pdf" and doc is not None:
                    for page in doc:
                        tp = None
                        if len(page.get_text("text").strip()) < 50:
                            try:
                                tp = page.get_textpage_ocr(flags=0, language='eng', dpi=150, full=True)
                            except Exception:
                                pass
                        
                        for target_string in strings_to_redact:
                            if target_string and len(str(target_string).strip()) > 4:
                                text_instances = page.search_for(str(target_string), textpage=tp) if tp else page.search_for(str(target_string))
                                for inst in text_instances:
                                    page.add_redact_annot(inst, fill=(0, 0, 0))
                                    
                        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_PIXELS)
                    doc.save(output_buffer, garbage=4, deflate=True)
                    doc.close()

                elif file_ext == "docx":
                    doc_docx = Document(io.BytesIO(file_bytes)) 
                    def replace_text_in_run(run):
                        for target_string in strings_to_redact:
                            if target_string and len(str(target_string).strip()) > 4:
                                if str(target_string) in run.text:
                                    run.text = run.text.replace(str(target_string), "[REDACTED]")

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

                zip_file.writestr(output_filename, output_buffer.getvalue())

            # --- CREATE THE EXCEL FILE ---
            df = pd.DataFrame(all_candidates_data)
            excel_buffer = io.BytesIO()
            with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name='Candidates')
            zip_file.writestr("Candidate_Summary_Data.xlsx", excel_buffer.getvalue())

        st.success("All documents processed!")
        st.download_button(
            label="Download Zip",
            data=zip_buffer.getvalue(),
            file_name="AI_Processed_CVs.zip",
            mime="application/zip"
        )
        
    except Exception as e:
        st.error(f"An error occurred while processing: {e}")
