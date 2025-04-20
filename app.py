import streamlit as st
import asyncio
import os
import tempfile
import traceback
import sys
from brand_extractor import BrandExtractor
import asyncio.exceptions

# Enable debug mode
st.set_page_config(page_title="Brand Extractor", layout="centered")
st.set_option('client.showErrorDetails', True)

# Create a temporary directory for reports
temp_dir = tempfile.mkdtemp()
st.write(f"Debug: Using temporary directory: {temp_dir}")

st.title("🌐 Brand Style Guide Extractor")
st.write("Enter a website URL to analyze and download a PDF branding report with colors, fonts, and logos.")

# Add debug mode toggle
debug_mode = st.sidebar.checkbox("Debug Mode", value=True)

url = st.text_input("Website URL", placeholder="https://www.example.com")

if st.button("Generate Report") and url:
    progress_text = st.empty()
    progress_bar = st.progress(0)
    
    try:
        async def run_extractor():
            try:
                progress_text.text("Setting up browser...")
                progress_bar.progress(10)
                
                # Install Playwright browsers if not already installed
                if not os.path.exists(os.path.expanduser("~/.cache/ms-playwright")):
                    progress_text.text("Installing required browsers...")
                    import subprocess
                    result = subprocess.run(["playwright", "install", "chromium"], 
                                         capture_output=True, text=True)
                    if debug_mode:
                        st.write(f"Debug: Playwright install output: {result.stdout}")
                        if result.stderr:
                            st.write(f"Debug: Playwright install errors: {result.stderr}")
                    if result.returncode != 0:
                        st.error(f"Playwright installation failed: {result.stderr}")
                        return None
                
                progress_text.text("Creating extractor instance...")
                progress_bar.progress(20)
                
                # Validate URL format
                if not url.startswith(('http://', 'https://')):
                    st.error("❌ URL must start with http:// or https://")
                    return None
                
                extractor = BrandExtractor(url, output_dir=temp_dir, auto_open=False, debug=debug_mode)
                
                progress_text.text("Starting website analysis...")
                progress_bar.progress(30)
                
                # Set a timeout for the extraction process
                try:
                    result = await asyncio.wait_for(extractor.extract_branding(), timeout=60)  # 60 second timeout
                    if debug_mode:
                        st.write(f"Debug: Raw extraction result: {result}")
                        
                    if not result:
                        st.error("❌ Extraction failed - no result returned")
                        return None
                        
                except asyncio.TimeoutError:
                    st.error("❌ The analysis took too long to complete. Please try again or try a different URL.")
                    return None
                except Exception as e:
                    st.error(f"❌ Error during extraction: {str(e)}")
                    if debug_mode:
                        st.write("Full error traceback:")
                        st.code(traceback.format_exc())
                    return None
                
                progress_bar.progress(90)
                progress_text.text("Finalizing report...")
                
                if result and 'pdf' in result:
                    if debug_mode:
                        st.write(f"Debug: PDF path: {result['pdf']}")
                        st.write(f"Debug: File exists: {os.path.exists(result['pdf'])}")
                        st.write(f"Debug: File size: {os.path.getsize(result['pdf']) if os.path.exists(result['pdf']) else 'N/A'}")
                    
                    if not os.path.exists(result['pdf']):
                        st.error("❌ PDF file was not created")
                        return None
                        
                    progress_bar.progress(100)
                    progress_text.text("Report generated successfully!")
                    return result['pdf']
                else:
                    if debug_mode:
                        st.error(f"Debug: Result object: {result}")
                    st.error("❌ No PDF generated in the result")
                    return None
                    
            except Exception as e:
                st.error(f"❌ Extraction error: {str(e)}")
                if debug_mode:
                    st.write("Full error traceback:")
                    st.code(traceback.format_exc())
                return None

        pdf_path = asyncio.run(run_extractor())

        if pdf_path and os.path.exists(pdf_path):
            st.success("✅ Report generated successfully!")
            with open(pdf_path, "rb") as f:
                st.download_button(
                    label="📄 Download PDF Report",
                    data=f,
                    file_name=os.path.basename(pdf_path),
                    mime="application/pdf"
                )
        else:
            st.error("❌ Failed to generate the report. Try another URL.")
            st.info("Please make sure the URL is accessible and includes the protocol (http:// or https://)")
            
    except Exception as e:
        st.error(f"❌ An error occurred: {str(e)}")
        if debug_mode:
            st.code(traceback.format_exc())
        st.info("Please try again with a different URL or contact support if the issue persists.")
    finally:
        # Clear progress indicators if they exist
        if 'progress_bar' in locals():
            progress_bar.empty()
        if 'progress_text' in locals():
            progress_text.empty()
