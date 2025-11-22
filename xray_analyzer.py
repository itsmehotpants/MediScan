import streamlit as st
import google.generativeai as genai
from PIL import Image, ImageDraw
import json
import datetime
import random # Used for random ID generation
import os
import time 
from dotenv import load_dotenv 

# --- PDF IMPORT SAFETY BLOCK ---
try:
    from pdf_gen import create_medical_pdf
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False
    def create_medical_pdf(*args, **kwargs):
        return None

# --- CONFIGURATION & CACHING ---
load_dotenv() 

# Try to get key from environment
API_KEY = os.getenv("GEMINI_API_KEY")

# --- PAGE SETUP ---
st.set_page_config(page_title="MediScan Dashboard", page_icon="🩺", layout="wide")

# --- CUSTOM CSS ---
st.markdown("""
<style>
    .stApp { background-color: #0E1117; }
    section[data-testid="stSidebar"] { background-color: #161B26; }
    .metric-card {
        background-color: #1F2937;
        border-left: 5px solid #3B82F6;
        padding: 15px;
        border-radius: 5px;
        margin-bottom: 10px;
    }
    .metric-label { color: #9CA3AF; font-size: 12px; font-weight: bold; }
    .metric-value { color: #FFFFFF; font-size: 24px; font-weight: bold; }
    .analysis-box {
        background-color: #1F2937;
        padding: 20px;
        border-radius: 10px;
        border: 1px solid #374151;
        color: #E5E7EB;
    }
    /* Tab Styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 24px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        white-space: pre-wrap;
        background-color: #1F2937;
        border-radius: 4px 4px 0px 0px;
        gap: 1px;
        padding-top: 10px;
        padding-bottom: 10px;
    }
    .stTabs [aria-selected="true"] {
        background-color: #3B82F6;
        color: white;
    }
    h1, h2, h3 { color: #FFFFFF !important; }
    p, li { color: #E5E7EB !important; }
</style>
""", unsafe_allow_html=True)

# --- SIDEBAR ---
with st.sidebar:
    st.title("🏥 MediScan AI")
    
    if not API_KEY:
        API_KEY = st.text_input("Enter Gemini API Key", type="password")
        if not API_KEY:
            st.warning("⚠️ Please enter an API Key to proceed.")
            st.stop()
            
    st.markdown("---")
    st.header("Patient Settings")
    p_name = st.text_input("Patient Name", "Rahul Kumar")
    p_age = st.number_input("Age", value=27)
    p_sex = st.selectbox("Sex", ["Male", "Female", "Other"])
    st.markdown("---")

# --- MODEL SETUP ---
@st.cache_resource
def load_gemini_model(api_key):
    genai.configure(api_key=api_key)
    return genai.GenerativeModel('gemini-2.0-flash')

try:
    model = load_gemini_model(API_KEY)
except Exception as e:
    st.error(f"Error configuring Gemini: {e}")
    st.stop()

# --- SESSION STATE MANAGEMENT ---

# 1. Initialize Random Patient Counter (Only runs once per session)
if "patient_counter" not in st.session_state: 
    # Generate a random number between 100 and 1000
    st.session_state.patient_counter = random.randint(100, 1000)

if "last_uploaded_file" not in st.session_state: st.session_state.last_uploaded_file = None

# Initialize Report ID with the random number
if "report_id" not in st.session_state: 
    st.session_state.report_id = f"PID-{st.session_state.patient_counter}"

if "analysis_result" not in st.session_state: st.session_state.analysis_result = None
if "deep_eval_result" not in st.session_state: st.session_state.deep_eval_result = None
if "chat_session" not in st.session_state: st.session_state.chat_session = None
if "chat_history" not in st.session_state: st.session_state.chat_history = []

# --- HELPER FUNCTIONS ---
def simulate_progress_bar(text="Processing..."):
    """Visual UX helper to show a progress bar"""
    progress_text = text
    my_bar = st.progress(0, text=progress_text)
    for percent_complete in range(100):
        time.sleep(0.005) # Fast simulation
        my_bar.progress(percent_complete + 1, text=progress_text)
    time.sleep(0.1)
    my_bar.empty()

def initial_scan(image):
    prompt = """
    Analyze this medical image.
    1. Identify the ORGAN.
    2. Return JSON ONLY. Format:
    {
        "organ": "Name",
        "findings": [{"condition": "Name", "severity": "Low/Med/High", "box": [ymin,xmin,ymax,xmax]}]
    }
    Important: "box" coordinates must be 0-1000 scale.
    """
    try:
        response = model.generate_content([prompt, image])
        text = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(text)
    except Exception as e:
        st.error(f"Scan Error: {e}")
        return None

def deep_evaluate(image, context):
    prompt = f"""
    Context: {json.dumps(context)}
    Provide a medical assessment.
    Format:
    - **Observation:** ...
    - **Severity:** ...
    - **Recommendation:** ...
    
    At the end, output strictly: Risk_Percentage: [0-100]%
    Example: "Risk_Percentage: 85%"
    """
    try:
        response = model.generate_content([prompt, image])
        return response.text
    except Exception as e:
        st.error(f"Analysis Error: {e}")
        return None

# --- MAIN UI ---
st.title("📊 Medical Diagnostic Dashboard")
current_datetime = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# Metrics Calculation
organ_val = "Waiting..."
condition_count = "0"
risk_val_display = "N/A" # String for display (e.g., "85%")
risk_color = "#3B82F6"

if st.session_state.analysis_result:
    res = st.session_state.analysis_result
    organ_val = res.get('organ', 'Unknown')
    condition_count = str(len(res.get('findings', [])))
    
    if st.session_state.deep_eval_result:
        import re
        # Updated Regex to look for Risk_Percentage
        match = re.search(r"Risk_Percentage:\s*(\d+)", st.session_state.deep_eval_result)
        if match:
            numeric_score = int(match.group(1))
            risk_val_display = f"{numeric_score}%" # Add Percentage Symbol
            
            # Dynamic Color Logic
            if numeric_score >= 75:
                risk_color = "#FF4B4B" # Red
            elif numeric_score >= 50:
                risk_color = "#FFC700" # Yellow
            else:
                risk_color = "#00B894" # Green

# Metrics Display
c1, c2, c3, c4 = st.columns(4)
c1.markdown(f'<div class="metric-card"><div class="metric-label">PATIENT ID</div><div class="metric-value">{st.session_state.report_id}</div></div>', unsafe_allow_html=True)
c2.markdown(f'<div class="metric-card"><div class="metric-label">ORGAN</div><div class="metric-value">{organ_val}</div></div>', unsafe_allow_html=True)
c3.markdown(f'<div class="metric-card"><div class="metric-label">FINDINGS</div><div class="metric-value">{condition_count}</div></div>', unsafe_allow_html=True)
c4.markdown(f'<div class="metric-card" style="border-left: 5px solid {risk_color}"><div class="metric-label">RISK PROBABILITY</div><div class="metric-value">{risk_val_display}</div></div>', unsafe_allow_html=True)

st.markdown("---")

uploaded_file = st.file_uploader("Upload X-Ray/MRI", type=['jpg', 'png', 'jpeg'])

if uploaded_file:
    # --- AUTO-INCREMENT ID LOGIC ---
    # Check if the uploaded file is different from the last one
    if uploaded_file.name != st.session_state.last_uploaded_file:
        
        # If this isn't the very first load, increment the random number
        if st.session_state.last_uploaded_file is not None:
            st.session_state.patient_counter += 1 
            
        st.session_state.report_id = f"PID-{st.session_state.patient_counter}" # Update ID
        st.session_state.last_uploaded_file = uploaded_file.name # Store new filename
        
        # Reset Analysis for new file
        st.session_state.analysis_result = None
        st.session_state.deep_eval_result = None
        st.session_state.chat_session = None
        st.session_state.chat_history = []
        
        # Show toast only if it's a new file upload (not page refresh)
        st.toast(f"New Patient ID Generated: {st.session_state.report_id}", icon="🆔")

    img = Image.open(uploaded_file)
    
    # --- TABBED INTERFACE ---
    tab1, tab2, tab3 = st.tabs(["👁️ Visual Scan", "📝 Clinical Report", "💬 MediScan Doctor"])
    
    # TAB 1: VISUAL SCAN
    with tab1:
        col_a, col_b = st.columns([1, 1])
        with col_a:
            st.subheader("Original Image")
            st.image(img, use_container_width=True)
            
        with col_b:
            st.subheader("Model Detection")
            if not st.session_state.analysis_result:
                if st.button("Start Scan", key="btn_scan", type="primary"):
                    simulate_progress_bar("Scanning image layers...")
                    with st.spinner("Identifying anomalies..."):
                        st.session_state.analysis_result = initial_scan(img)
                        if st.session_state.analysis_result: 
                            st.toast("Scan Completed Successfully!", icon="✅")
                            st.rerun()
            
            # Draw Boxes
            
            # Draw Boxes
            if st.session_state.analysis_result:
                annotated = img.copy()
                draw = ImageDraw.Draw(annotated)
                w, h = annotated.size
                for f in st.session_state.analysis_result.get('findings', []):
                    if 'box' in f:
                        y1, x1, y2, x2 = f['box']
                        draw.rectangle([x1/1000*w, y1/1000*h, x2/1000*w, y2/1000*h], outline="red", width=4)
                st.image(annotated, use_container_width=True)
                annotated.save("temp_annotated.jpg")

  # TAB 2: CLINICAL REPORT
    with tab2:
        st.subheader("Diagnostic Report")
        
        # 1. Logic to Generate Report
        if st.session_state.analysis_result and not st.session_state.deep_eval_result:
            st.info("Visual scan complete. Click below to generate the full clinical text report.")
            
            if st.button("Generate Assessment", key="btn_eval", type="primary"):
                simulate_progress_bar("Synthesizing clinical insights...")
                with st.spinner("Drafting detailed report..."):
                    # Generate the text
                    st.session_state.deep_eval_result = deep_evaluate(img, st.session_state.analysis_result)
                    
                    # Reset chat so it knows about the new report
                    st.session_state.chat_session = None 
                    st.toast("Report Generated Successfully!", icon="📄")
                    st.rerun()
        
        # 2. Display Report (The Fix is here)
        if st.session_state.deep_eval_result:
            # We add 'style="white-space: pre-wrap;"' to preserve the line breaks and bullet points
            st.markdown(f"""
            <div class="analysis-box" style="white-space: pre-wrap; font-family: sans-serif; line-height: 1.6;">
                {st.session_state.deep_eval_result}
            </div>
            """, unsafe_allow_html=True)
            
            st.markdown("---")
            
            # 3. Download Section
            col_dl_1, col_dl_2 = st.columns([1, 2])
            with col_dl_1:
                if PDF_AVAILABLE:
                    pdf_bytes = create_medical_pdf({
                        "name": p_name, "age": p_age, "sex": p_sex,
                        "id": st.session_state.report_id, "date": current_datetime
                    }, st.session_state.analysis_result, st.session_state.deep_eval_result, "temp_annotated.jpg")
                    
                    st.download_button(
                        label="📥 Download Report PDF", 
                        data=pdf_bytes, 
                        file_name=f"Report_{st.session_state.report_id}.pdf", 
                        mime="application/pdf",
                        type="primary"
                    )
                else:
                    st.warning("PDF Generator module not found.")
            
            with col_dl_2:
                # Optional: Add a regenerate button in case the output was bad
                if st.button("🔄 Regenerate Report"):
                    st.session_state.deep_eval_result = None
                    st.rerun()
    # TAB 3: CHAT
    with tab3:
        st.subheader("💬 Interactive Consultation")
        if st.session_state.deep_eval_result:
            if st.session_state.chat_session is None:
                # Start chat with context
                history = [
                    {"role": "user", "parts": [f"Context: {st.session_state.deep_eval_result}. Act as a doctor."]},
                    {"role": "model", "parts": ["Understood. I am ready to assist based on this analysis."]}
                ]
                st.session_state.chat_session = model.start_chat(history=history)
                st.session_state.chat_history = []

            # Chat Interface
            chat_container = st.container(height=400)
            for msg in st.session_state.chat_history:
                chat_container.chat_message(msg['role']).write(msg['content'])

            if prompt := st.chat_input("Ask about the diagnosis..."):
                st.session_state.chat_history.append({"role": "user", "content": prompt})
                chat_container.chat_message("user").write(prompt)
                
                try:
                    with st.spinner("Assistant typing..."):
                        response = st.session_state.chat_session.send_message(prompt)
                    st.session_state.chat_history.append({"role": "assistant", "content": response.text})
                    chat_container.chat_message("assistant").write(response.text)
                except Exception as e:
                    st.error(f"Chat Error: {e}")
        else:
             st.info("⚠️ Please generate a Clinical Report (Tab 2) before consulting the AI Assistant.")

elif not uploaded_file:
    # Clean State
    st.session_state.analysis_result = None
    st.session_state.deep_eval_result = None