import streamlit as st
import os
from dotenv import load_dotenv
from utils.file_parser import parse_excel, parse_pdf
from utils.analysis import analyze_report, scan_pdf_reports, scan_excel_reports
import pandas as pd
from datetime import datetime
import json
import re

# Load environment variables
load_dotenv()

st.set_page_config(page_title="Financial Analyst Agent", page_icon="📊", layout="wide")

# Initialize session state for reports history and scan results
if 'reports_history' not in st.session_state:
    st.session_state.reports_history = []
if 'scanned_reports' not in st.session_state:
    st.session_state.scanned_reports = None

st.title("📊 Financial Analyst Agent")
st.markdown("Upload your financial reports (Excel or PDF) and get AI-powered analysis.")

# Sidebar for API Key and Actions
with st.sidebar:
    st.header("Configuration")
    api_key = st.text_input("OpenAI API Key", type="password", value=os.getenv("OPENAI_API_KEY", ""))
    if not api_key:
        st.warning("Please enter your OpenAI API Key to proceed.")
    
    st.divider()
    
    # New Report Button
    if st.button("🆕 Nuevo Reporte", type="primary", use_container_width=True):
        st.session_state.show_new_report = True
        st.session_state.scanned_reports = None  # Reset scan on new report
        st.rerun()
    
    # Show reports count
    if st.session_state.reports_history:
        st.info(f"📊 Reportes generados: {len(st.session_state.reports_history)}")
        
        if st.button("🗑️ Limpiar Historial", use_container_width=True):
            st.session_state.reports_history = []
            st.rerun()

# File Upload
uploaded_file = st.file_uploader("Choose a file", type=["xlsx", "xls", "pdf"])

if uploaded_file and api_key:
    st.info(f"File '{uploaded_file.name}' uploaded successfully.")
    
    # Process file based on type
    file_extension = uploaded_file.name.split(".")[-1].lower()
    
    parsed_data = None
    
    try:
        if file_extension in ["xlsx", "xls"]:
            with st.spinner("Parsing Excel file..."):
                parsed_data = parse_excel(uploaded_file)
                st.success("Excel file parsed successfully!")
                
                
                # --- EXCEL SHEET SELECTION ---
                st.divider()
                st.subheader("📂 Configuración de Lectura")
                
                sheet_names = list(parsed_data.keys())
                analysis_scope = st.radio("Alcance del Análisis:", ["Analizar Todo el Archivo", "Seleccionar Hoja Específica"])
                
                if analysis_scope == "Seleccionar Hoja Específica" and len(sheet_names) > 0:
                    selected_sheet = st.selectbox("Selecciona la hoja a analizar:", sheet_names)
                    # Filter parsed_data to keep only the selected sheet
                    parsed_data = {selected_sheet: parsed_data[selected_sheet]}
                    st.info(f"✅ Se limitará el análisis a la hoja: **{selected_sheet}**")
                
                # Show preview of data (Filtered or Full)
                st.text("Vista Previa:")
                if isinstance(parsed_data, dict):
                    for sheet_name, content in parsed_data.items():
                        with st.expander(f"Previsualizar: {sheet_name}"):
                            st.dataframe(content['values'].head())
                            formulas = content.get('formulas', {})
                            if formulas:
                                st.write(f"Fórmulas encontradas: {len(formulas)}")
                
        elif file_extension == "pdf":
            with st.spinner("Extracting text from PDF..."):
                parsed_data = parse_pdf(uploaded_file)
                st.success("PDF text extracted successfully!")
                with st.expander("Extracted Text Preview"):
                    st.text(parsed_data[:1000] + "...")
        
        
        # --- DOC SCAN & SELECTION LOGIC ---
        selected_focus = None
        
        # Enable scan for both PDF and Excel
        if file_extension in ['pdf', 'xlsx', 'xls']:
            st.divider()
            st.subheader("🔍 Detección de Reportes")
            
            # Button to trigger scan
            if st.button("🔎 Escanear contenido del Documento"):
                with st.spinner("Analizando estructura del documento..."):
                    
                    scan_json = ""
                    if file_extension == 'pdf':
                        scan_json = scan_pdf_reports(parsed_data, api_key)
                    else:
                        # Excel
                        scan_json = scan_excel_reports(parsed_data, api_key)
                    
                    # Extract JSON block
                    json_match = re.search(r'```json\s*\n(.*?)\n```', scan_json, re.DOTALL)
                    if not json_match:
                         # Try without newlines or different format
                         json_match = re.search(r'```json(.*?)```', scan_json, re.DOTALL)
                    
                    if json_match:
                        try:
                            st.session_state.scanned_reports = json.loads(json_match.group(1))
                            st.success(f"Se encontraron {len(st.session_state.scanned_reports)} reportes posibles.")
                        except json.JSONDecodeError as e:
                            st.error(f"Error al procesar la lista de reportes: {str(e)}")
                            st.text(scan_json)
                    else:
                         # Fallback if no JSON block found, try raw parse or show error
                         try:
                            # Sometimes models output raw JSON without markdown
                            st.session_state.scanned_reports = json.loads(scan_json)
                         except:
                            st.warning("No se pudo estructurar la lista de reportes automáticamente.")
                            st.text(scan_json)

            # Display selection if reports are found
            if st.session_state.scanned_reports:
                report_options = {f"{r['title']} ({r['location']}) - {r['description']}": r['title'] for r in st.session_state.scanned_reports}
                report_options["Todos / Análisis General"] = None
                
                selection = st.radio(
                    "Selecciona el reporte que deseas analizar:",
                    options=list(report_options.keys()),
                    index=0
                )
                
                selected_focus = report_options[selection]
                
                if selected_focus:
                    st.info(f"🎯 **Enfoque seleccionado**: {selected_focus}")
                else:
                    st.info("🌐 Se analizará todo el documento.")
                    
        # --- END DOC SCAN LOGIC ---

        # Analysis Button
        if st.button("Analyze Report", type="primary"):
            with st.spinner("Analyzing with OpenAI..."):
                # Pass selected_focus to analysis
                analysis_result = analyze_report(parsed_data, file_extension, api_key, focus_context=selected_focus)
                
                # Extract CSV from code block - try multiple patterns
                csv_content = None
                csv_df = None
                
                # Try different regex patterns to extract CSV
                patterns = [
                    r'```csv\s*\n(.*?)\n```',  # Standard markdown with newlines
                    r'```csv\s*\r?\n(.*?)\r?\n```',  # With optional carriage returns
                    r'```csv(.*?)```',  # Without requiring newlines
                ]
                
                for pattern in patterns:
                    csv_match = re.search(pattern, analysis_result, re.DOTALL)
                    if csv_match:
                        csv_content = csv_match.group(1).strip()
                        break
                
                # If CSV content was found, try to parse it
                if csv_content:
                    try:
                        from io import StringIO
                        csv_df = pd.read_csv(StringIO(csv_content), on_bad_lines='skip', quotechar='"', skipinitialspace=True, encoding='utf-8')
                        st.success(f"✅ CSV extraído correctamente ({len(csv_df)} filas)")
                    except Exception as e:
                        st.warning(f"CSV encontrado pero no se pudo parsear como DataFrame: {str(e)}")
                else:
                    st.warning("⚠️ No se encontró un bloque CSV en la respuesta del análisis")
                
                # Save to history
                report_entry = {
                    'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    'filename': uploaded_file.name + (f" [{selected_focus}]" if selected_focus else ""),
                    'analysis': analysis_result,
                    'csv_content': csv_content,
                    'csv_df': csv_df
                }
                st.session_state.reports_history.append(report_entry)
                st.rerun()
                
    except Exception as e:
        st.error(f"An error occurred: {str(e)}")

elif uploaded_file and not api_key:
    st.error("Please provide an API Key to analyze the file.")

# Display all reports from history
if st.session_state.reports_history:
    st.divider()
    st.header("📚 Historial de Reportes")
    
    for idx, report in enumerate(reversed(st.session_state.reports_history), 1):
        report_num = len(st.session_state.reports_history) - idx + 1
        
        with st.expander(f"📄 Reporte #{report_num} - {report['filename']} ({report['timestamp']})", expanded=(idx == 1)):
            st.markdown("### 🤖 Análisis Financiero")
            st.markdown(report['analysis'])
            
            if report['csv_content']:
                st.markdown("### 📋 Datos Estructurados (CSV)")
                
                if report['csv_df'] is not None:
                    st.dataframe(report['csv_df'])
                    st.info(f"📊 Total de filas: {len(report['csv_df'])}")
                else:
                    st.code(report['csv_content'], language='csv')
                
                # Validate CSV content before creating download button
                if report['csv_content'] and len(report['csv_content'].strip()) > 0:
                    try:
                        # Generate simple, clean filename
                        base_name = report['filename'].rsplit('.', 1)[0]  # Remove extension
                        # Clean the base name to remove special characters
                        import re
                        clean_name = re.sub(r'[^\w\s-]', '', base_name).strip()
                        clean_name = re.sub(r'[-\s]+', '_', clean_name)
                        filename = f"{clean_name}_analisis.csv"
                        
                        # Encode CSV content to UTF-8 with BOM for Excel compatibility
                        csv_bytes = report['csv_content'].encode('utf-8-sig')
                        
                        st.download_button(
                            label=f"📥 Descargar {filename}",
                            data=csv_bytes,
                            file_name=filename,
                            mime="text/csv; charset=utf-8",
                            key=f"dl_{report_num}",
                            help=f"Descargar archivo CSV ({len(csv_bytes)} bytes)"
                        )
                        st.caption(f"💡 **Nombre del archivo**: `{filename}` | **Tamaño**: {len(csv_bytes):,} bytes")
                    except Exception as e:
                        st.error(f"❌ Error al preparar la descarga: {str(e)}")
                else:
                    st.error("❌ El contenido CSV está vacío")
            else:
                st.info("No se generó un bloque CSV estructurado en esta respuesta.")
