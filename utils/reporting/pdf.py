#!/usr/bin/env python3
"""
Professional CRO Audit PDF Report Generator
Matches the Taurist Technologies report styling from the Airtame PDF
"""

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate,
    Table,
    TableStyle,
    Paragraph,
    Spacer,
    Image,
    PageBreak,
    KeepTogether,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import json
import os

# Register Pretendard font (with fallback)
FONT_NAME = "Pretendard"
FONT_NAME_BOLD = "Pretendard-Bold"


def extract_why_it_matters(issue):
    """
    Extract 'Why It Matters' content from either format:
    - New format: separate 'why_it_matters' field
    - Old format: concatenated in 'description' after '\n\nWhy it matters: '

    This provides backward compatibility with cached results.
    """
    # Try new format first (separate field)
    if issue.get("why_it_matters"):
        return issue["why_it_matters"]

    # Try old concatenated format (cached results)
    description = issue.get("description", "")
    if "\n\nWhy it matters: " in description:
        parts = description.split("\n\nWhy it matters: ", 1)
        return parts[1]  # Return everything after the split

    return ""  # No why_it_matters content found


def register_fonts():
    """Register Pretendard font if available, otherwise use system fallback"""
    global FONT_NAME, FONT_NAME_BOLD

    # Check if Pretendard fonts exist
    pretendard_path = "/home/claude/pretendard_fonts/public/static"

    if os.path.exists(f"{pretendard_path}/Pretendard-Regular.ttf"):
        try:
            pdfmetrics.registerFont(
                TTFont("Pretendard", f"{pretendard_path}/Pretendard-Regular.ttf")
            )
            pdfmetrics.registerFont(
                TTFont("Pretendard-Bold", f"{pretendard_path}/Pretendard-Bold.ttf")
            )
            print("✓ Using Pretendard font")
        except:
            # Fallback to DejaVu Sans (clean, modern sans-serif)
            FONT_NAME = "DejaVu-Sans"
            FONT_NAME_BOLD = "DejaVu-Sans-Bold"
            try:
                pdfmetrics.registerFont(
                    TTFont(
                        "DejaVu-Sans", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
                    )
                )
                pdfmetrics.registerFont(
                    TTFont(
                        "DejaVu-Sans-Bold",
                        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                    )
                )
                print("✓ Using DejaVu Sans font (Pretendard not found)")
            except:
                # Ultimate fallback to Helvetica
                FONT_NAME = "Helvetica"
                FONT_NAME_BOLD = "Helvetica-Bold"
                print("✓ Using Helvetica font (system fonts not found)")
    else:
        # Fallback to DejaVu Sans
        FONT_NAME = "DejaVu-Sans"
        FONT_NAME_BOLD = "DejaVu-Sans-Bold"
        try:
            pdfmetrics.registerFont(
                TTFont("DejaVu-Sans", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
            )
            pdfmetrics.registerFont(
                TTFont(
                    "DejaVu-Sans-Bold",
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                )
            )
            print("✓ Using DejaVu Sans font (Pretendard not available)")
        except:
            FONT_NAME = "Helvetica"
            FONT_NAME_BOLD = "Helvetica-Bold"
            print("✓ Using Helvetica font")


# Custom color palette matching the Airtame PDF
COLORS = {
    "primary_red": colors.HexColor("#DC3545"),
    "dark_gray": colors.HexColor("#1F2937"),
    "medium_gray": colors.HexColor("#6B7280"),
    "light_gray": colors.HexColor("#F3F4F6"),
    "pale_gray": colors.HexColor("#F9FAFB"),
    "blue": colors.HexColor("#3B82F6"),
    "warning_bg": colors.HexColor("#FEF3C7"),
    "warning_text": colors.HexColor("#92400E"),
    "success_bg": colors.HexColor("#D1FAE5"),
    "success_text": colors.HexColor("#047A55"),
    "white": colors.white,
    "pink": colors.HexColor("#EC4899"),
    "fair_yellow": colors.HexColor("#F59E0B"),
    "good_green": colors.HexColor("#10B981"),
}


def create_custom_styles():
    """Create custom paragraph styles matching the PDF design"""
    styles = getSampleStyleSheet()

    # Title style
    styles.add(
        ParagraphStyle(
            name="CustomTitle",
            parent=styles["Heading1"],
            fontSize=24,
            textColor=COLORS["dark_gray"],
            spaceAfter=6,
            alignment=TA_CENTER,
            fontName=FONT_NAME_BOLD,
        )
    )

    # Subtitle style
    styles.add(
        ParagraphStyle(
            name="CustomSubtitle",
            parent=styles["Normal"],
            fontSize=11,
            textColor=COLORS["medium_gray"],
            spaceAfter=20,
            alignment=TA_CENTER,
            fontName=FONT_NAME,
        )
    )

    # URL style
    styles.add(
        ParagraphStyle(
            name="URLStyle",
            parent=styles["Normal"],
            fontSize=16,
            textColor=COLORS["blue"],
            spaceAfter=4,
            alignment=TA_CENTER,
            fontName=FONT_NAME_BOLD,
        )
    )

    # Date style
    styles.add(
        ParagraphStyle(
            name="DateStyle",
            parent=styles["Normal"],
            fontSize=10,
            textColor=COLORS["medium_gray"],
            spaceAfter=20,
            alignment=TA_CENTER,
            fontName=FONT_NAME,
        )
    )

    # Section heading
    styles.add(
        ParagraphStyle(
            name="SectionHeading",
            parent=styles["Heading1"],
            fontSize=16,
            textColor=COLORS["dark_gray"],
            spaceAfter=8,
            spaceBefore=8,
            fontName=FONT_NAME_BOLD,
        )
    )

    # Subsection heading
    styles.add(
        ParagraphStyle(
            name="SubsectionHeading",
            parent=styles["Heading2"],
            fontSize=11,
            textColor=COLORS["dark_gray"],
            spaceAfter=3,
            spaceBefore=3,
            fontName=FONT_NAME_BOLD,
        )
    )

    # Issue title
    styles.add(
        ParagraphStyle(
            name="IssueTitle",
            parent=styles["Heading2"],
            fontSize=13,
            textColor=COLORS["dark_gray"],
            spaceAfter=6,
            spaceBefore=6,
            fontName=FONT_NAME_BOLD,
        )
    )

    # Label style (DESCRIPTION, etc.)
    styles.add(
        ParagraphStyle(
            name="LabelStyle",
            parent=styles["Normal"],
            fontSize=10,
            textColor=COLORS["medium_gray"],
            spaceAfter=4,
            fontName=FONT_NAME_BOLD,
        )
    )

    # Body text
    styles.add(
        ParagraphStyle(
            name="CustomBodyText",
            parent=styles["Normal"],
            fontSize=11,
            textColor=COLORS["dark_gray"],
            spaceAfter=4,
            alignment=TA_JUSTIFY,
            fontName=FONT_NAME,
            leading=15,
        )
    )

    # Warning box text
    styles.add(
        ParagraphStyle(
            name="WarningText",
            parent=styles["Normal"],
            fontSize=11,
            textColor=COLORS["warning_text"],
            spaceAfter=4,
            alignment=TA_JUSTIFY,
            fontName=FONT_NAME,
            leading=15,
            leftIndent=10,
            rightIndent=10,
        )
    )

    # Success box text
    styles.add(
        ParagraphStyle(
            name="SuccessText",
            parent=styles["Normal"],
            fontSize=11,
            textColor=COLORS["success_text"],
            spaceAfter=4,
            alignment=TA_JUSTIFY,
            fontName=FONT_NAME,
            leading=15,
            leftIndent=10,
            rightIndent=10,
        )
    )

    return styles


def create_metrics_table(data):
    """Create 4 scorecard metrics in a single row"""

    # Helper function to map color names to ReportLab colors
    def get_scorecard_color(color_name):
        color_map = {
            "green": COLORS["good_green"],
            "yellow": COLORS["fair_yellow"],
            "red": COLORS["primary_red"],
        }
        return color_map.get(color_name.lower(), COLORS["medium_gray"])

    # Get conversion score data
    conversion_data = data.get("conversion_rate_increase_potential", {})
    conversion_value = conversion_data.get("percentage", "N/A")
    conversion_confidence = conversion_data.get("confidence", "")

    # Get scorecard data
    scorecards = data.get("scorecards", {})
    site_perf = scorecards.get("site_performance", {})
    conv_potential = scorecards.get("conversion_potential", {})
    mobile_exp = scorecards.get("mobile_experience", {})

    # Create 4-column table with all scores in one row
    scorecard_data = [
        # Row 1: Score values
        [
            conversion_value,
            f"{site_perf.get('score', 'N/A')}/100",
            f"{conv_potential.get('score', 'N/A')}/100",
            f"{mobile_exp.get('score', 'N/A')}/100",
        ],
        # Row 2: Labels
        [
            "Potential Uplift",
            "Site Performance",
            "Conversion Score",
            "Mobile Experience",
        ],
    ]

    scorecard_table = Table(
        scorecard_data,
        colWidths=[1.875 * inch, 1.875 * inch, 1.875 * inch, 1.875 * inch],
        spaceBefore=0,
        spaceAfter=0,
        hAlign="CENTER",
    )

    # Get colors for each scorecard
    confidence_color = (
        COLORS["good_green"]
        if conversion_confidence == "High"
        else COLORS["fair_yellow"]
    )
    site_perf_color = get_scorecard_color(site_perf.get("color", "yellow"))
    conv_pot_color = get_scorecard_color(conv_potential.get("color", "yellow"))
    mobile_color = get_scorecard_color(mobile_exp.get("color", "yellow"))

    scorecard_table.setStyle(
        TableStyle(
            [
                # Value row styling
                ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                ("FONTSIZE", (0, 0), (-1, 0), 18),
                ("FONTNAME", (0, 0), (-1, 0), FONT_NAME_BOLD),
                ("TEXTCOLOR", (0, 0), (-1, 0), COLORS["dark_gray"]),
                ("TOPPADDING", (0, 0), (-1, 0), 12),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 18),
                # Label row styling
                ("ALIGN", (0, 1), (-1, 1), "CENTER"),
                ("FONTSIZE", (0, 1), (-1, 1), 9),
                ("FONTNAME", (0, 1), (-1, 1), FONT_NAME),
                ("TEXTCOLOR", (0, 1), (-1, 1), COLORS["medium_gray"]),
                ("TOPPADDING", (0, 1), (-1, 1), 8),
                ("BOTTOMPADDING", (0, 1), (-1, 1), 12),
                # Individual card borders
                ("BOX", (0, 0), (0, -1), 1, COLORS["light_gray"]),
                ("BOX", (1, 0), (1, -1), 1, COLORS["light_gray"]),
                ("BOX", (2, 0), (2, -1), 1, COLORS["light_gray"]),
                ("BOX", (3, 0), (3, -1), 1, COLORS["light_gray"]),
                # White backgrounds
                ("BACKGROUND", (0, 0), (-1, -1), COLORS["white"]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                # Colored top borders for visual distinction
                ("BACKGROUND", (0, 0), (0, 0), confidence_color.clone(alpha=0.2)),
                ("BACKGROUND", (1, 0), (1, 0), site_perf_color.clone(alpha=0.2)),
                ("BACKGROUND", (2, 0), (2, 0), conv_pot_color.clone(alpha=0.2)),
                ("BACKGROUND", (3, 0), (3, 0), mobile_color.clone(alpha=0.2)),
                # Equal padding for all cells to ensure centered text
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )

    return scorecard_table


def create_executive_summary_section(data, styles):
    """Create executive summary with clean styling (no borders)"""
    elements = []

    # Section title
    elements.append(Paragraph("Executive Summary", styles["SectionHeading"]))
    elements.append(Spacer(1, 0.06 * inch))

    # Overview
    elements.append(Paragraph("Overview", styles["SubsectionHeading"]))

    # Create overview box with background (no border)
    overview_table = Table(
        [[Paragraph(data["executive_summary"]["overview"], styles["CustomBodyText"])]],
        colWidths=[7.5 * inch],
    )
    overview_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), COLORS["pale_gray"]),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    elements.append(overview_table)
    elements.append(Spacer(1, 0.08 * inch))

    # How to Act
    elements.append(Paragraph("How to Act", styles["SubsectionHeading"]))

    # Static "How to Act" text with bullet list
    how_to_act_intro = "Turn the insights below into quick wins. Start small, move fast, measure impact."

    how_to_act_bullets = [
        "Pick the top 1 to 2 items by impact, confidence, and effort",
        "Write a simple hypothesis for each change and the metric it should move",
        "Ship the smallest change that proves the idea and keep other variables steady",
        "Track one primary metric for 7 to 14 days or until stable, then log the result",
        "Low traffic: Ship sequential improvements and compare pre vs post. Healthy traffic: Run A/B tests",
    ]

    # Build formatted text with bullets
    bullet_text = (
        how_to_act_intro
        + "<br/><br/>"
        + "<br/>".join([f"• {item}" for item in how_to_act_bullets])
    )

    # Create action box with background (no border)
    action_table = Table(
        [[Paragraph(bullet_text, styles["CustomBodyText"])]],
        colWidths=[7.5 * inch],
    )
    action_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), COLORS["pale_gray"]),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    elements.append(action_table)
    elements.append(Spacer(1, 0.12 * inch))

    return elements


def create_issue_section(issue, issue_number, styles):
    """Create a single issue section with proper styling"""
    elements = []

    # Issue number and title - bold black number inline with title
    issue_heading_text = f'<b>{issue_number}.</b>   {issue["title"]}'
    title_para = Paragraph(issue_heading_text, styles["IssueTitle"])
    elements.append(title_para)
    elements.append(Spacer(1, 0.08 * inch))

    # Description section
    elements.append(Paragraph("DESCRIPTION", styles["LabelStyle"]))
    desc_table = Table(
        [[Paragraph(issue["description"], styles["CustomBodyText"])]],
        colWidths=[7.5 * inch],
    )
    desc_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), COLORS["pale_gray"]),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    elements.append(desc_table)
    elements.append(Spacer(1, 0.06 * inch))

    # Why It Matters section (yellow background)
    elements.append(Paragraph("Why It Matters", styles["SubsectionHeading"]))
    why_table = Table(
        [[Paragraph(extract_why_it_matters(issue), styles["WarningText"])]],
        colWidths=[7.5 * inch],
    )
    why_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), COLORS["warning_bg"]),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    elements.append(why_table)
    elements.append(Spacer(1, 0.06 * inch))

    # Recommendations section (green background)
    elements.append(Paragraph("Recommendations", styles["SubsectionHeading"]))

    # Handle both old format (string with newlines) and new format (array)
    if "recommendations" in issue and isinstance(issue["recommendations"], list):
        # New API format: recommendations as array
        recommendations = issue["recommendations"]
    elif "recommendation" in issue:
        # Old format: recommendation as string with newlines
        recommendations = issue["recommendation"].split("\n")
    else:
        # Fallback: empty recommendations
        recommendations = []

    rec_text = "<br/>".join(
        [
            f"• {rec.strip()}" if rec.strip() else ""
            for rec in recommendations
            if rec.strip()
        ]
    )

    rec_table = Table(
        [[Paragraph(rec_text, styles["SuccessText"])]], colWidths=[7.5 * inch]
    )
    rec_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), COLORS["success_bg"]),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    elements.append(rec_table)
    elements.append(Spacer(1, 0.12 * inch))

    # Add horizontal divider line
    divider_table = Table([[""]], colWidths=[7.5 * inch], rowHeights=[1])
    divider_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), COLORS["light_gray"]),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    elements.append(divider_table)
    elements.append(Spacer(1, 0.28 * inch))  # ~20px extra spacing

    return elements


def create_footer_section(styles, data):
    """Create the footer CTA section"""
    elements = []

    # Disclaimer text
    disclaimer_table = Table(
        [
            [
                Paragraph(
                    "This represents a preliminary high-level assessment. Further data is needed to produce more detailed and impactful results.",
                    styles["CustomBodyText"],
                )
            ]
        ],
        colWidths=[7.5 * inch],
    )
    disclaimer_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), COLORS["light_gray"]),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("LEFTPADDING", (0, 0), (-1, -1), 20),
                ("RIGHTPADDING", (0, 0), (-1, -1), 20),
                ("TOPPADDING", (0, 0), (-1, -1), 12),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
            ]
        )
    )
    elements.append(disclaimer_table)
    elements.append(Spacer(1, 0.12 * inch))

    # CTA Button
    cta_style = ParagraphStyle(
        "CTAButton",
        parent=styles["Normal"],
        fontSize=14,
        textColor=COLORS["white"],
        alignment=TA_CENTER,
        fontName=FONT_NAME_BOLD,
    )
    # Make button clickable with Calendly link
    cta_text = '<link href="https://calendly.com/taurist/cro-strategy-call-founder-led" color="white">☎ Book A Call</link>'
    cta_table = Table([[Paragraph(cta_text, cta_style)]], colWidths=[2.5 * inch])
    cta_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), COLORS["pink"]),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 12),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
                ("ROUNDEDCORNERS", [10, 10, 10, 10]),
            ]
        )
    )

    # Center the CTA button
    cta_container = Table([[cta_table]], colWidths=[7.5 * inch])
    cta_container.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ]
        )
    )
    elements.append(cta_container)
    elements.append(Spacer(1, 0.15 * inch))

    # Footer metadata
    meta_style = ParagraphStyle(
        "MetaStyle",
        parent=styles["Normal"],
        fontSize=9,
        textColor=COLORS["medium_gray"],
        alignment=TA_CENTER,
        fontName=FONT_NAME,
    )

    # Format date for footer
    from datetime import datetime

    try:
        analyzed_date = datetime.fromisoformat(
            data["analyzed_at"].replace("Z", "+00:00")
        )
        footer_date = analyzed_date.strftime("%B %d, %Y")
    except (ValueError, AttributeError):
        footer_date = "November 3, 2025"  # Fallback

    elements.append(
        Paragraph(f"CRO Audit Report | Generated on {footer_date}", meta_style)
    )

    total_issues = data.get("total_issues_identified", len(data.get("issues", [])))
    shown_issues = len(data.get("issues", []))

    elements.append(
        Paragraph(
            f"Total Issues Identified: {total_issues} | Critical Issues Shown: {shown_issues}",
            meta_style,
        )
    )

    return elements


def generate_pdf(audit_data, output_path=None):
    """
    Generate the complete PDF report

    Args:
        audit_data: Dictionary containing analysis results with structure:
            - url: Website URL analyzed
            - analyzed_at: Timestamp of analysis
            - issues: List of issue dictionaries
            - Optional: executive_summary, scores, metrics
        output_path: Optional file path to save PDF. If None, returns BytesIO buffer

    Returns:
        BytesIO buffer if output_path is None, otherwise None (saves to file)
    """
    from io import BytesIO

    # Create BytesIO buffer or use file path
    if output_path:
        pdf_file = output_path
    else:
        pdf_file = BytesIO()

    # Create the PDF document with smaller margins
    doc = SimpleDocTemplate(
        pdf_file,
        pagesize=letter,
        rightMargin=0.5 * inch,
        leftMargin=0.5 * inch,
        topMargin=0.5 * inch,
        bottomMargin=0.5 * inch,
    )

    # Container for the 'Flowable' objects
    elements = []

    # Get custom styles
    styles = create_custom_styles()

    # Add logo if it exists
    # Construct path relative to project root
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    logo_path = os.path.join(project_root, "assets", "Taurist Logo Black.png")

    if os.path.exists(logo_path):
        try:
            logo = Image(logo_path, width=1.2 * inch, height=0.4 * inch)
            logo.hAlign = "LEFT"
            elements.append(logo)
            elements.append(Spacer(1, 0.3 * inch))
        except Exception as e:
            print(f"Warning: Could not load logo: {e}")
            elements.append(Spacer(1, 0.1 * inch))
    else:
        # Logo not found, skip it
        print(f"Warning: Logo not found at {logo_path}")
        elements.append(Spacer(1, 0.1 * inch))

    # Add title
    elements.append(Paragraph("5 win CRO Analysis Report", styles["CustomTitle"]))
    elements.append(
        Paragraph("Powered by Taurist Technologies Inc", styles["CustomSubtitle"])
    )
    elements.append(Spacer(1, 0.1 * inch))

    # Add URL and date
    elements.append(Paragraph(audit_data["url"], styles["URLStyle"]))

    # Format date as MM/DD/YYYY
    from datetime import datetime

    try:
        # Parse ISO format date and convert to MM/DD/YYYY
        analyzed_date = datetime.fromisoformat(
            audit_data["analyzed_at"].replace("Z", "+00:00")
        )
        formatted_date = analyzed_date.strftime("%m/%d/%Y")
    except (ValueError, AttributeError):
        # Fallback if parsing fails
        formatted_date = audit_data["analyzed_at"]

    elements.append(Paragraph(f"Analyzed: {formatted_date}", styles["DateStyle"]))
    elements.append(Spacer(1, 0.12 * inch))

    # Add metrics dashboard
    elements.append(create_metrics_table(audit_data))
    elements.append(Spacer(1, 0.18 * inch))

    # Add executive summary
    elements.extend(create_executive_summary_section(audit_data, styles))

    # Add page break AFTER executive summary
    elements.append(PageBreak())

    # Add issues section header
    elements.append(
        Paragraph(
            f'Critical Issues Identified (5 of {audit_data["total_issues_identified"]})',
            styles["SectionHeading"],
        )
    )
    elements.append(Spacer(1, 0.2 * inch))

    # Add each issue (first 5)
    for idx, issue in enumerate(audit_data["issues"][:5], 1):
        issue_elements = create_issue_section(issue, idx, styles)
        # Keep each issue together on the same page
        elements.append(KeepTogether(issue_elements))

    # Add footer section
    elements.extend(create_footer_section(styles, audit_data))

    # Build the PDF
    doc.build(elements)

    if output_path:
        print(f"✅ PDF Report created successfully: {output_path}")
        return None
    else:
        pdf_file.seek(0)
        return pdf_file


def main():
    """Main function to generate the PDF"""

    # Register fonts first
    register_fonts()

    # Load audit data
    audit_data = {
        "url": "https://mifold.com/",
        "analyzed_at": "October 25, 2025",
        "issues": [
            {
                "title": "Weak Value Proposition and Benefit Clarity in Hero Section",
                "description": "The hero headline 'The Foldable Booster—10x Smaller, Just as Safe' focuses on product features rather than parent benefits. The supporting text is generic and doesn't address core parent concerns like convenience, travel ease, or safety confidence. The value proposition lacks emotional resonance and doesn't clearly communicate why parents should choose this over traditional boosters.",
                "why_it_matters": "The hero section is the first impression for 85% of visitors and determines bounce rate within 8 seconds. A weak value proposition can reduce conversion rates by 30-50% as visitors don't immediately understand why they need this product. Parents making safety-related purchases need clear benefit-focused messaging to overcome purchase hesitation.",
                "recommendation": "Replace generic headline with specific outcome-focused messaging like 'Turn Any Screen Into a Wireless Collaboration Hub in 30 Seconds'\nAdd benefit-driven subheading that addresses specific pain points like 'No more cable hunting, complicated setups, or meeting delays - just instant screen sharing that works'",
            },
            {
                "title": "Insufficient Trust Signals and Safety Credentials Above the Fold",
                "description": "Safety certifications, crash test ratings, and regulatory approvals are buried below the fold or missing entirely from the hero section. For a child safety product, parents need immediate reassurance about safety standards. The current hero section shows brand logos but lacks specific safety certifications that parents actively look for.",
                "why_it_matters": "Child safety products have inherently high purchase anxiety. Studies show safety-related products see 40-60% higher conversion rates when safety credentials are prominently displayed above the fold. Parents will abandon the page within seconds if they don't see immediate safety validation for car seat products.",
                "recommendation": "Add prominent safety badges above the fold: 'FMVSS 213 Certified', 'European ECE R44/04 Approved', 'Crash Tested & Proven'\nInclude a trust bar with safety certifications directly under the hero headline before the CTA button",
            },
            {
                "title": "Generic and Weak Call-to-Action Buttons",
                "description": "The main CTA uses generic 'Shop Now' text which lacks urgency and doesn't communicate value. The button doesn't stand out visually against the background and appears small relative to the hero content. There are multiple competing CTAs visible simultaneously without clear hierarchy.",
                "why_it_matters": "CTA optimization typically yields 15-25% conversion improvements. Generic CTAs like 'Shop Now' convert 20-30% worse than benefit-focused alternatives. The weak visual prominence means users may not even notice the primary conversion path, directly impacting sales.",
                "recommendation": "Change CTA text to benefit-focused: 'Get Your Portable Car Seat' or 'Secure Safe Travel Today'\nIncrease button size by 40% and use contrasting colors (bright orange or red) to improve visibility and click-through rates",
            },
            {
                "title": "Product Selection Confusion and Analysis Paralysis",
                "description": "The product showcase section presents multiple product options (different models/colors) without clear differentiation or guidance on which product fits which use case. Parents face analysis paralysis when presented with choices without clear decision-making criteria. No 'recommended' or 'most popular' indicators help guide selection.",
                "why_it_matters": "Hick's Law states that decision time increases logarithmically with choices. Product pages with too many undifferentiated options see 15-30% lower conversion rates. Parents shopping for safety products need clear guidance to overcome decision anxiety and complete purchases.",
                "recommendation": "Add clear product differentiation labels: 'Best for Travel', 'Most Popular', 'Best Value' to help guide selection\nImplement a product finder quiz: 'Find Your Perfect Booster in 30 Seconds' to reduce choice overwhelm",
            },
            {
                "title": "Missing Urgency and Scarcity Elements",
                "description": "The page lacks any urgency or scarcity indicators such as limited-time offers, low stock notifications, or shipping deadlines. The purchasing experience feels static without compelling reasons to buy today versus later. No seasonal urgency despite travel products having natural urgency triggers (upcoming trips, holidays).",
                "why_it_matters": "Urgency and scarcity elements typically increase conversion rates by 10-25% by triggering loss aversion psychology. Without urgency, visitors often leave intending to return later but never do, resulting in abandoned purchase intent and lost revenue.",
                "recommendation": "Add shipping urgency: 'Order by 2PM for Same-Day Shipping' or 'Get It Before Your Weekend Trip'\nInclude inventory indicators: 'Only 12 left in stock' or seasonal messaging: 'Don't Miss Holiday Travel Season - Ships in 24hrs'",
            },
        ],
        "total_issues_identified": 12,
        "executive_summary": {
            "overview": "Mifold's homepage demonstrates strong visual design and product presentation but suffers from critical conversion barriers that likely reduce purchase completion by 30-50%. The primary issues center around weak benefit-focused messaging in the hero section, insufficient safety credentialing for anxious parents, generic CTAs that fail to drive action, product selection confusion that creates decision paralysis, and missing urgency elements that allow visitors to defer purchase decisions. These issues compound to create a high-friction experience for parents who need clear guidance and confidence when purchasing child safety products.",
            "how_to_act": "Prioritize implementation starting with highest-impact front-funnel optimizations: first, rewrite the hero value proposition to focus on parent benefits and add safety certifications above the fold to address purchase anxiety immediately. Next, optimize the primary CTA for better visibility and benefit-focused copy. Then address structural elements by adding product selection guidance and decision-making aids. Finally, layer in urgency elements and shipping incentives. Frame each change as a testable hypothesis and implement using A/B testing methodology, starting with the hero section changes that will impact 100% of visitors before moving to deeper-funnel optimizations.",
        },
        "cro_analysis_score": {"score": 62, "rating": "Fair"},
        "site_performance_score": {"score": 75, "rating": "Good"},
        "conversion_rate_increase_potential": {
            "percentage": "25-45%",
            "confidence": "High",
        },
    }

    # Generate the PDF
    output_path = "/mnt/user-data/outputs/Mifold_CRO_Audit_Report.pdf"
    generate_pdf(audit_data, output_path)


if __name__ == "__main__":
    main()
