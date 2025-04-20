import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
import requests
import re
from collections import Counter
import os
from datetime import datetime
from reportlab.lib import colors as reportlab_colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
import argparse
import sys
import json
import webbrowser
import traceback

class BrandExtractor:
    def __init__(self, url, output_dir='reports', auto_open=False):
        self.url = url
        self.output_dir = output_dir
        self.auto_open = auto_open
        self.soup = None
        self.styles = {}
        self.css_variables = {}
        self.fonts = set()
        self.colors = set()
        self.themes = {}
        self.font_frequency = Counter()
        self.color_frequency = Counter()
        self.logo_path = None

    async def fetch_page(self):
        try:
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.set_extra_http_headers({
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0 Safari/537.36'
                })
                await page.goto(self.url, wait_until='load', timeout=60000)
                await page.wait_for_timeout(3000)  # Wait 3 seconds for JS to settle

                
                # Extract inline and external CSS
                await self.extract_css(page)
                
                content = await page.content()
                self.soup = BeautifulSoup(content, 'lxml')

                # Try to find a logo image
                logo_found = False
                logo_tag = self.soup.find('img', {'alt': re.compile(r'logo', re.I)})
                if logo_tag and logo_tag.get('src'):
                    logo_url = logo_tag['src']
                    if logo_url.startswith('//'):
                        logo_url = 'https:' + logo_url
                    elif logo_url.startswith('/'):
                        logo_url = self.url.rstrip('/') + logo_url
                    elif not logo_url.startswith('http'):
                        logo_url = self.url.rstrip('/') + '/' + logo_url
                    try:
                        logo_response = requests.get(logo_url, stream=True)
                        if logo_response.status_code == 200:
                            logo_ext = os.path.splitext(logo_url.split('?')[0])[-1].lower()
                            logo_path = os.path.join(self.output_dir, 'logo.png')
                            os.makedirs(self.output_dir, exist_ok=True)
                            if logo_ext == '.svg':
                                try:
                                    import cairosvg
                                    cairosvg.svg2png(bytestring=logo_response.content, write_to=logo_path)
                                except Exception as svg_err:
                                    print(f"Error converting SVG logo to PNG: {svg_err}")
                                    return False
                            else:
                                with open(logo_path, 'wb') as f:
                                    f.write(logo_response.content)
                            self.logo_path = logo_path
                            logo_found = True
                    except Exception as e:
                        print(f"Error downloading logo image: {e}")

                # If no logo image was found, try favicon or og:image
                if not logo_found:
                    icon_link = self.soup.find('link', rel=re.compile(r'(icon|shortcut icon)', re.I))
                    if not icon_link:
                        meta_logo = self.soup.find('meta', property='og:image')
                        if meta_logo and meta_logo.get('content'):
                            logo_url = meta_logo['content']
                        else:
                            logo_url = None
                    else:
                        logo_url = icon_link.get('href')

                    if logo_url:
                        if logo_url.startswith('//'):
                            logo_url = 'https:' + logo_url
                        elif logo_url.startswith('/'):
                            logo_url = self.url.rstrip('/') + logo_url
                        elif not logo_url.startswith('http'):
                            logo_url = self.url.rstrip('/') + '/' + logo_url
                        try:
                            logo_response = requests.get(logo_url, stream=True)
                            if logo_response.status_code == 200:
                                logo_ext = os.path.splitext(logo_url.split('?')[0])[-1].lower()
                                if logo_ext not in ['.jpg', '.jpeg', '.png']:
                                    logo_ext = '.png'
                                logo_path = os.path.join(self.output_dir, f'logo{logo_ext}')
                                os.makedirs(self.output_dir, exist_ok=True)
                                with open(logo_path, 'wb') as f:
                                    f.write(logo_response.content)
                                self.logo_path = logo_path
                        except Exception as e:
                            print(f"Error downloading fallback logo: {e}")

                return True
        except Exception as e:
            print(f"Error fetching page: {e}")
            return False
            
    async def extract_css(self, page):
        try:
            # Extract inline styles
            inline_styles = await page.evaluate('''
                () => {
                    const styles = [];
                    const styleElements = document.querySelectorAll('style');
                    styleElements.forEach(style => {
                        styles.push({
                            type: 'inline',
                            content: style.textContent
                        });
                    });
                    return styles;
                }
            ''')
            
            for i, style in enumerate(inline_styles):
                self.styles[f'inline_style_{i}'] = style['content']
            
            # Extract external stylesheets
            external_stylesheets = await page.evaluate('''
                () => {
                    const links = [];
                    const linkElements = document.querySelectorAll('link[rel="stylesheet"]');
                    linkElements.forEach(link => {
                        if (link.href) {
                            links.push(link.href);
                        }
                    });
                    return links;
                }
            ''')
            
            for i, stylesheet_url in enumerate(external_stylesheets):
                try:
                    response = requests.get(stylesheet_url, timeout=10)
                    if response.status_code == 200:
                        self.styles[f'external_style_{i}'] = response.text
                except Exception as e:
                    print(f"Error fetching external stylesheet {stylesheet_url}: {e}")
            
            # Extract inline style attributes
            inline_attrs = await page.evaluate('''
                () => {
                    const elements = document.querySelectorAll('[style]');
                    const styles = [];
                    elements.forEach(el => {
                        styles.push(el.getAttribute('style'));
                    });
                    return styles;
                }
            ''')
            
            if inline_attrs:
                self.styles['inline_attributes'] = ' '.join(inline_attrs)
                
            # Extract computed styles for common elements
            computed_styles = await page.evaluate('''
                () => {
                    const elements = document.querySelectorAll('body, h1, h2, h3, p, a, button, .logo, .header, .footer, .nav, .main, .container');
                    const styles = {};
                    elements.forEach((el, index) => {
                        const computed = window.getComputedStyle(el);
                        const important = [
                            'color', 'background-color', 'font-family', 'font-size', 
                            'font-weight', 'border-color', 'border-radius'
                        ];
                        const elementStyles = {};
                        important.forEach(prop => {
                            elementStyles[prop] = computed.getPropertyValue(prop);
                        });
                        styles[el.tagName.toLowerCase() + '_' + index] = elementStyles;
                    });
                    return styles;
                }
            ''')
            
            # Convert computed styles to CSS format
            computed_css = []
            for selector, props in computed_styles.items():
                style_block = []
                for prop, value in props.items():
                    if value:
                        style_block.append(f"{prop}: {value};")
                if style_block:
                    computed_css.append(f"#{selector} {{ {' '.join(style_block)} }}")
            
            if computed_css:
                self.styles['computed_styles'] = ' '.join(computed_css)
                
            print(f"Found {len(self.styles)} style sources")
            
        except Exception as e:
            print(f"Error extracting CSS: {e}")

    def analyze_styles(self):
        if not self.styles:
            print("Warning: No styles were extracted. Style analysis may be incomplete.")
            return
            
        root_var_pattern = re.compile(r'--(.*?):\s*(.*?);')
        font_pattern = re.compile(r'font-family:\s*([^;]+)')
        color_pattern = re.compile(r'#([0-9a-fA-F]{3,6})')
        rgb_pattern = re.compile(r'rgb\((\d+),\s*(\d+),\s*(\d+)\)')
        rgba_pattern = re.compile(r'rgba\((\d+),\s*(\d+),\s*(\d+),\s*([0-9.]+)\)')
        
        # Extract CSS variables from :root
        for content in self.styles.values():
            root_matches = re.findall(r':root\s*\{([^}]*)\}', str(content))
            for block in root_matches:
                for var, value in root_var_pattern.findall(block):
                    self.css_variables[f"var(--{var.strip()})"] = value.strip()

        # Extract fonts and colors
        for style_content in self.styles.values():
            # Process fonts
            font_matches = font_pattern.findall(str(style_content))
            for match in font_matches:
                fonts = [f.strip().strip("'\"") for f in match.split(',')]
                for font in fonts:
                    if font.lower() not in ['inherit', 'initial', 'unset', 'serif', 'sans-serif', 'monospace', 'cursive', 'fantasy']:
                        if font.startswith('var('):
                            font = self.css_variables.get(font, font)
                        self.font_frequency[font] += 1
                        self.fonts.add(font)

            # Process hex colors
            color_matches = color_pattern.findall(str(style_content))
            for match in color_matches:
                hex_code = match.lower()
                if len(hex_code) == 3:
                    hex_code = ''.join([c * 2 for c in hex_code])
                color = f'#{hex_code}'
                self.color_frequency[color] += 1
                self.colors.add(color)
                
            # Process RGB colors
            rgb_matches = rgb_pattern.findall(str(style_content))
            for r, g, b in rgb_matches:
                r, g, b = int(r), int(g), int(b)
                hex_color = f'#{r:02x}{g:02x}{b:02x}'
                self.color_frequency[hex_color] += 1
                self.colors.add(hex_color)
                
            # Process RGBA colors (convert to hex, ignoring alpha)
            rgba_matches = rgba_pattern.findall(str(style_content))
            for r, g, b, a in rgba_matches:
                r, g, b = int(r), int(g), int(b)
                hex_color = f'#{r:02x}{g:02x}{b:02x}'
                self.color_frequency[hex_color] += 1
                self.colors.add(hex_color)

    def get_top_fonts(self, limit=5):
        return [font for font, _ in self.font_frequency.most_common(limit)]

    def get_top_colors(self, limit=5):
        return [color for color, _ in self.color_frequency.most_common(limit)]

    def extract_fonts(self):
        self.analyze_styles()

    def extract_colors(self):
        self.analyze_styles()

    def analyze_themes(self):
        self.themes = {
            'primary_colors': self.get_top_colors(3),
            'fonts': self.get_top_fonts(3),
            'color_scheme': list(self.colors)
        }

    def generate_pdf_report(self):
        os.makedirs(self.output_dir, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{self.output_dir}/brand_report_{timestamp}.pdf"

        primary_colors = self.get_top_colors(3)
        secondary_colors = self.get_top_colors(6)[3:] if len(self.get_top_colors(6)) > 3 else []
        primary_fonts = self.get_top_fonts(3)

        doc = SimpleDocTemplate(filename, pagesize=letter)
        styles = getSampleStyleSheet()
        story = []

        if self.logo_path:
            try:
                story.append(Image(self.logo_path, width=1.5 * inch, height=1.5 * inch))
                story.append(Spacer(1, 12))
            except Exception as e:
                print(f"Error adding logo to PDF: {e}")

        story.append(Paragraph("Brand Style Guide", ParagraphStyle('Title', parent=styles['Title'], fontSize=24, spaceAfter=30)))
        story.append(Paragraph("Website Analysis", styles['Heading2']))
        story.append(Paragraph(f"URL: {self.url}", styles['Normal']))
        story.append(Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", styles['Normal']))
        story.append(Spacer(1, 20))

        # Create color swatches
        def create_color_table(colors):
            if not colors:
                return Table([["No colors detected"]])
                
            color_data = []
            color_data.append(["Color", "Hex Code", "Usage Count"])
            
            for color in colors:
                try:
                    # Convert hex to ReportLab color
                    hex_code = color.lstrip('#')
                    r = int(hex_code[0:2], 16) / 255
                    g = int(hex_code[2:4], 16) / 255
                    b = int(hex_code[4:6], 16) / 255
                    
                    # Create a small color swatch
                    color_box = Table([['']], colWidths=[0.3*inch], rowHeights=[0.3*inch])
                    color_box.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, -1), (r, g, b)),
                        ('BOX', (0, 0), (-1, -1), 0.5, reportlab_colors.black),
                    ]))
                    
                    color_data.append([color_box, color, str(self.color_frequency[color])])
                except Exception as e:
                    print(f"Error creating swatch for color {color}: {e}")
                    color_data.append(["Error", color, str(self.color_frequency[color])])
            
            table = Table(color_data)
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), reportlab_colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), reportlab_colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('GRID', (0, 0), (-1, -1), 0.5, reportlab_colors.grey),
            ]))
            return table

        story.append(Paragraph("Typography", styles['Heading2']))
        story.append(Paragraph("Primary Fonts", styles['Heading3']))
        if primary_fonts:
            font_data = [['Font', 'Usage Count']] + [[font, str(self.font_frequency[font])] for font in primary_fonts]
            font_table = Table(font_data)
            font_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), reportlab_colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), reportlab_colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('GRID', (0, 0), (-1, -1), 0.5, reportlab_colors.grey),
            ]))
            story.append(font_table)
        else:
            story.append(Paragraph("No fonts detected", styles['Normal']))
        story.append(Spacer(1, 12))

        story.append(Paragraph("Color Palette", styles['Heading2']))
        story.append(Paragraph("Primary Colors", styles['Heading3']))
        story.append(create_color_table(primary_colors))
        story.append(Spacer(1, 12))

        if secondary_colors:
            story.append(Paragraph("Secondary Colors", styles['Heading3']))
            story.append(create_color_table(secondary_colors))
            story.append(Spacer(1, 12))

        doc.build(story)

        if self.auto_open:
            webbrowser.open(filename)

        return filename

    def generate_json_report(self):
        os.makedirs(self.output_dir, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{self.output_dir}/brand_report_{timestamp}.json"
        data = {
            'url': self.url,
            'fonts': {
                'all': list(self.fonts),
                'top_used': self.get_top_fonts(5)
            },
            'colors': {
                'all': list(self.colors),
                'top_used': self.get_top_colors(5)
            },
            'themes': self.themes,
            'stylesheets': list(self.styles.keys())
        }
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)
        return filename

    async def extract_branding(self):
        try:
            print(f"Starting fetch_page for URL: {self.url}")
            if not await self.fetch_page():
                print("Error: Failed to fetch page")
                return None
            
            print("Starting font extraction...")
            try:
                self.extract_fonts()
            except Exception as e:
                print(f"Error extracting fonts: {str(e)}")
                traceback.print_exc()
                return None
            
            print("Starting color extraction...")
            try:
                self.extract_colors()
            except Exception as e:
                print(f"Error extracting colors: {str(e)}")
                traceback.print_exc()
                return None
            
            print("Starting theme analysis...")
            try:
                self.analyze_themes()
            except Exception as e:
                print(f"Error analyzing themes: {str(e)}")
                traceback.print_exc()
                return None
            
            print("Starting PDF report generation...")
            try:
                pdf_path = self.generate_pdf_report()
                if not pdf_path:
                    print("Error: PDF generation returned None")
                    return None
                print(f"PDF report generated at: {pdf_path}")
            except Exception as e:
                print(f"Error generating PDF report: {str(e)}")
                traceback.print_exc()
                return None
            
            print("Starting JSON report generation...")
            try:
                json_path = self.generate_json_report()
                if not json_path:
                    print("Error: JSON generation returned None")
                    return None
                print(f"JSON report generated at: {json_path}")
            except Exception as e:
                print(f"Error generating JSON report: {str(e)}")
                traceback.print_exc()
                return None
            
            print(f"Reports generated successfully: PDF={pdf_path}, JSON={json_path}")
            return {'pdf': pdf_path, 'json': json_path}
        except Exception as e:
            print(f"Error in extract_branding: {str(e)}")
            traceback.print_exc()
            return None

def parse_arguments():
    parser = argparse.ArgumentParser(description='Extract branding information from a website.')
    parser.add_argument('--url', '-u', help='Website URL to analyze')
    parser.add_argument('--output', '-o', help='Output directory for reports', default='reports')
    parser.add_argument('--open', action='store_true', help='Auto-open the generated PDF after completion')
    return parser.parse_args()

async def main():
    args = parse_arguments()
    url = args.url
    if not url:
        print("Error: URL is required")
        sys.exit(1)

    print(f"\nAnalyzing website: {url}\nThis may take a few moments...")
    extractor = BrandExtractor(url, args.output, auto_open=args.open)
    result = await extractor.extract_branding()
    if result:
        print("\nReports generated:")
        print(f"PDF Report: {result['pdf']}")
        print(f"JSON Report: {result['json']}")
    else:
        print("Failed to analyze the website.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
        sys.exit(0)
    except Exception as e:
        print(f"An error occurred: {e}")
        sys.exit(1)