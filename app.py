import streamlit as st
import asyncio
import os
import tempfile
import traceback
import sys
from brand_extractor import BrandExtractor

# Set page config
st.set_page_config(page_title="Brand Extractor", layout="centered")

# Create a temporary directory for reports
temp_dir = tempfile.mkdtemp()
st.write(f"Debug: Using temporary directory: {temp_dir}")

st.title("🌐 Brand Style Guide Extractor")
st.write("Enter a website URL to analyze and download a PDF branding report with colors, fonts, and logos.")

url = st.text_input("Website URL", placeholder="https://www.example.com")

if st.button("Generate Report") and url:
    with st.spinner("Analyzing website. This may take a moment..."):
        try:
            async def run_extractor():
                try:
                    st.write("Debug: Starting Playwright setup...")
                    # Install Playwright browsers if not already installed
                    if not os.path.exists(os.path.expanduser("~/.cache/ms-playwright")):
                        st.info("Installing required browsers...")
                        import subprocess
                        result = subprocess.run(["playwright", "install", "chromium"], 
                                             capture_output=True, text=True)
                        st.write(f"Debug: Playwright install output: {result.stdout}")
                        if result.returncode != 0:
                            st.error(f"Playwright installation failed: {result.stderr}")
                            return None
                    
                    st.write(f"Debug: Creating BrandExtractor instance for URL: {url}")
                    extractor = BrandExtractor(url, output_dir=temp_dir, auto_open=False)
                    
                    st.write("Debug: Starting extraction process...")
                    result = await extractor.extract_branding()
                    st.write(f"Debug: Extraction result: {result}")
                    
                    if result and 'pdf' in result:
                        st.write(f"Debug: PDF path from result: {result['pdf']}")
                        if os.path.exists(result['pdf']):
                            st.write(f"Debug: PDF file exists at path")
                            return result['pdf']
                        else:
                            st.error(f"Debug: PDF file does not exist at path: {result['pdf']}")
                            return None
                    else:
                        st.error("Debug: No PDF path in extraction result")
                        return None
                        
                except Exception as e:
                    st.error(f"Extraction error: {str(e)}")
                    st.code(traceback.format_exc())
                    return None

            st.write("Debug: Running extractor...")
            pdf_path = asyncio.run(run_extractor())
            st.write(f"Debug: Extractor completed, PDF path: {pdf_path}")

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
            st.code(traceback.format_exc())
            st.info("Please try again with a different URL or contact support if the issue persists.")
