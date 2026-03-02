import streamlit as st
import fitz  # PyMuPDF
import re
import io
import zipfile
import pandas as pd
import json
import google.generativeai as genai
from docx import Document

st.set_page_config(page_title="CV Redactor & AI Extractor", page_icon="📄")
st.title("Bulk CV Redactor & AI Data Extractor")
st.write("Upload CVs to redact contact info AND generate an AI-enriched Excel summary.")

# Safely load the API Key from Streamlit Secrets
try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    # Using the fast model for text extraction
    model = genai.GenerativeModel('gemini-2.5-flash')
except Exception as e:
    st.error("⚠️ Gemini API Key not found. Please add it to Streamlit Secrets.")

uploaded_files = st.file_uploader("Upload candidate CVs", type=["pdf", "docx"], accept_multiple_files=True)

if uploaded_files:
    st.info(f"Processing {len(uploaded_files)} document(s)...")
    
    # Strict regex for REDACTION only
    email_pattern = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
    phone_pattern = re.compile(r"\+?\d{1,4}?[-.\s]?\(?\d{1,3}?\)?[-.\s]?\d{1,4}[-.\s]?\d{1,4}[-.\s]?\d{1,9}")
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

                # --- PDF LOGIC ---
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
                        for pattern in patterns:
                            for match in pattern.finditer(text):
                                sensitive_text = match.group()
                                text_instances = page.search_for(sensitive_text, textpage=tp) if tp else page.search_for(sensitive_text)
                                for inst in text_instances:
                                    page.add_redact_annot(inst, fill=(0, 0, 0))
                        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_PIXELS)
                    doc.save(output_buffer, garbage=4, deflate=True)
                    doc.close()

                # --- WORD LOGIC ---
                elif file_ext == "docx":
                    docx_bytes = uploaded_file.read()
                    doc = Document(io.BytesIO(docx_bytes))
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

                # Write redacted CV to zip
                zip_file.writestr(output_filename, output_buffer.getvalue())

                # --- AI DATA EXTRACTION FOR EXCEL ---
                ai_prompt = f"""
                You are an expert recruitment assistant. Analyze the following CV text and extract the candidate's details into a strict JSON format.
                Use exactly these keys: "Name", "Qualification", "Age", "Email", "Phone", "Current Position", "Nationality", "Current Location".
                If a piece of information is not present in the text, use "Not Found" as the value. Do not guess.
                Return ONLY the raw JSON object, without any markdown formatting or explanations.
                
                CV Text:
                {full_text_for_extraction[:8000]}
                """
                
                try:
                    # Ask the AI to read the CV
                    response = model.generate_content(ai_prompt)
                    # Clean up the response to ensure it's pure JSON
                    json_text = response.text.strip().removeprefix('```json').removesuffix('```').strip()
                    extracted_data = json.loads(json_text)
                except Exception as e:
                    # Fallback if the AI gets confused by a weirdly formatted CV
                    extracted_data = {
                        "Name": "AI Error", "Qualification": "AI Error", "Age": "AI Error", 
                        "Email": "AI Error", "Phone": "AI Error", "Current Position": "AI Error", 
                        "Nationality": "AI Error", "Current Location": "AI Error"
                    }

                # Add the File Name and the AI's data to our master list
                candidate_record = {"File Name": uploaded_file.name}
                candidate_record.update(extracted_data)
                all_candidates_data.append(candidate_record)

            # --- CREATE THE EXCEL FILE ---
            df = pd.DataFrame(all_candidates_data)
            excel_buffer = io.BytesIO()
            with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name='Candidates')
            zip_file.writestr("Candidate_Summary_Data.xlsx", excel_buffer.getvalue())

        st.success("All documents processed and data extracted via AI!")
        st.download_button(
            label="Download Zip (Redacted CVs + AI Excel Data)",
            data=zip_buffer.getvalue(),
            file_name="Processed_CVs_and_Data.zip",
            mime="application/zip"
        )
        
    except Exception as e:
        st.error(f"An error occurred while processing: {e}")

