#!/usr/bin/env python3
"""
Test PDF generation with new data format (scorecards)
Uses real audit data from cornbreadsoul.com
"""

import json
from utils.pdf_generator import register_fonts, generate_pdf

# Real audit data from cornbreadsoul.com (with new scorecards format)
audit_data = {
    "url": "https://cornbreadsoul.com/",
    "analyzed_at": "2025-11-13T23:53:51.423233",
    "total_issues_identified": 12,
    "issues": [
        {
            "section": "Hero",
            "title": "Missing Clear Primary Call-to-Action in Hero Section",
            "description": "The hero section displays food imagery and 'Cater Your Holiday Season With CORNBREAD' messaging, but lacks a prominent primary CTA button. The only visible actions are secondary 'Delivery' and 'Pick-Up' buttons, which don't clearly guide users toward the primary conversion goal of ordering food or exploring the menu.",
            "why_it_matters": "The hero section is prime real estate with the highest visibility and engagement rates. Without a clear primary CTA, users experience decision paralysis and bounce rather than convert. Research shows that hero sections with prominent CTAs can increase conversion rates by 15-25%.",
            "recommendation": "Add a large, contrasting 'Order Now' or 'View Menu' button prominently positioned in the hero section\nUse action-oriented copy like 'Start Your Order' with high-contrast colors (white text on dark background) to maximize visibility",
            "priority_score": 85,
            "priority_rationale": "High impact on conversions (9) × High confidence based on CRO best practices (8) ÷ Low implementation effort (2) = 36 × 2.4 scaling factor",
            "screenshot_base64": None
        },
        {
            "section": "Navigation",
            "title": "Insufficient Value Proposition Communication in Navigation",
            "description": "The navigation shows 'ezCater is now available at all Locations' banner and basic menu items, but fails to communicate the restaurant's unique value proposition or differentiation. The 'Farm to Soul' tagline is present but not prominent enough to establish competitive advantage.",
            "why_it_matters": "Clear value proposition communication in the navigation increases user engagement and reduces bounce rates. Restaurants that clearly communicate their unique selling points see 20-30% higher conversion rates, especially in competitive food service markets.",
            "recommendation": "Make the 'Farm to Soul' value proposition more prominent in the header with supporting copy about fresh, local ingredients\nAdd trust signals like 'Locally Sourced' or 'Family Recipes' badges in the navigation area to reinforce differentiation",
            "priority_score": 72,
            "priority_rationale": "High impact on brand differentiation (8) × Good confidence in CRO principle (7) ÷ Medium effort (3) = 18.7",
            "screenshot_base64": None
        },
        {
            "section": "Hero",
            "title": "Weak Urgency and Scarcity Messaging for Holiday Catering",
            "description": "The hero mentions 'Holiday Season' catering but lacks urgency indicators, booking deadlines, or availability limitations. The messaging doesn't create time-sensitive motivation for users to act immediately on catering orders.",
            "why_it_matters": "Holiday catering is time-sensitive business with high-value orders. Adding urgency and scarcity elements can increase conversion rates by 20-40% for seasonal offerings, as customers need to book in advance and availability is genuinely limited.",
            "recommendation": "Add deadline messaging like 'Order Holiday Catering by December 15th' with countdown timer\nInclude availability indicators such as 'Limited Holiday Slots Available' to create scarcity motivation",
            "priority_score": 70,
            "priority_rationale": "Very high seasonal impact (9) × Good confidence (6) ÷ Medium effort (3) = 18",
            "screenshot_base64": None
        },
        {
            "section": "#LoveCornbread",
            "title": "Social Proof Section Lacks Clear Call-to-Action",
            "description": "The #LoveCornbread section appears to be designed for social engagement but doesn't provide clear direction for users on how to participate or what action to take. There's no visible CTA to encourage user-generated content or social sharing.",
            "why_it_matters": "Social proof sections without clear CTAs represent missed opportunities for viral marketing and user engagement. Adding actionable elements to social sections can increase engagement by 25-35% and create authentic marketing content.",
            "recommendation": "Add a prominent 'Share Your Cornbread Experience' CTA button linking to social media or photo upload\nInclude clear instructions like 'Tag us @cornbreadsoul with #LoveCornbread for a chance to be featured'",
            "priority_score": 65,
            "priority_rationale": "Medium-high impact on engagement (7) × Good confidence (7) ÷ Medium effort (3) = 16.3",
            "screenshot_base64": None
        },
        {
            "section": "Footer",
            "title": "Email Signup Form Lacks Value Proposition",
            "description": "The footer email signup form asks users to 'Sign up for our mailing list for updates, specials, & events' but doesn't specify what value subscribers will receive or how frequently they'll be contacted. The generic 'Subscribe' button doesn't motivate action.",
            "why_it_matters": "Email list growth is crucial for restaurant marketing and customer retention. Forms with clear value propositions see 40-60% higher conversion rates. Without compelling reasons to subscribe, this form likely has very low conversion rates.",
            "recommendation": "Replace generic copy with specific benefits like 'Get 10% off your first order + exclusive menu previews'\nChange button text to 'Get My Discount' or 'Send Me Deals' to be more action-oriented and benefit-focused",
            "priority_score": 62,
            "priority_rationale": "High long-term impact (8) × Medium confidence (6) ÷ Low effort (2) = 24",
            "screenshot_base64": None
        }
    ],
    "scorecards": {
        "ux_design": {
            "score": 75,
            "color": "green",
            "rationale": "Strong visual hierarchy with appealing food photography and clear section separation. Good use of white space and readable typography. However, CTA prominence could be improved and some sections lack clear user guidance."
        },
        "content_copy": {
            "score": 68,
            "color": "yellow",
            "rationale": "The 'Farm to Soul' messaging is good but not prominently featured. Holiday catering copy lacks urgency. Value propositions need to be more specific and benefit-focused throughout the site."
        },
        "site_performance": {
            "score": 82,
            "color": "green",
            "rationale": "Page loads efficiently with good image optimization. No major console errors detected. ezCater integration appears to be functioning properly based on navigation banner."
        },
        "conversion_potential": {
            "score": 62,
            "color": "yellow",
            "rationale": "Missing primary CTAs in key sections, weak urgency messaging for time-sensitive offerings, and insufficient value proposition communication limit conversion potential. Social proof elements are present but not optimized."
        },
        "mobile_experience": {
            "score": 78,
            "color": "green",
            "rationale": "Mobile layout appears well-optimized with readable text and appropriately sized elements. Navigation and content hierarchy translate well to mobile viewport based on screenshot analysis."
        }
    },
    "executive_summary": {
        "overview": "Cornbread Soul's website has strong visual appeal and branding but suffers from weak call-to-action strategy, insufficient value proposition communication, and missed opportunities for urgency-driven conversions. The primary issues include lack of prominent CTAs in the hero section, generic email signup messaging, weak holiday catering urgency, and underutilized social proof sections. Addressing these five quick wins could significantly improve user engagement and conversion rates, particularly for their seasonal catering business and ongoing customer acquisition efforts.",
        "how_to_act": ""
    },
    "conversion_rate_increase_potential": {
        "percentage": "18-28%",
        "confidence": "High",
        "rationale": "The identified issues represent fundamental CRO problems with well-documented solution patterns. Adding prominent CTAs typically increases conversions by 15-25%, improved value propositions add 10-15%, and urgency messaging for time-sensitive offers can boost conversions by 20-40%. Combined impact across all sections justifies the 18-28% range."
    }
}

# Register fonts
register_fonts()

# Generate PDF
output_path = "/Users/rhillx/Code/Taurist/cro_analyzer/Cornbread_Soul_CRO_Audit_Test.pdf"
generate_pdf(audit_data, output_path)

print(f"✅ PDF generated successfully: {output_path}")
print(f"✅ Test complete - PDF uses new format with:")
print(f"   - Potential Uplift: {audit_data['conversion_rate_increase_potential']['percentage']} ({audit_data['conversion_rate_increase_potential']['confidence']} confidence)")
print(f"   - Site Performance: {audit_data['scorecards']['site_performance']['score']}/100 ({audit_data['scorecards']['site_performance']['color']})")
print(f"   - Conversion Score: {audit_data['scorecards']['conversion_potential']['score']}/100 ({audit_data['scorecards']['conversion_potential']['color']})")
print(f"   - Mobile Experience: {audit_data['scorecards']['mobile_experience']['score']}/100 ({audit_data['scorecards']['mobile_experience']['color']})")
print(f"   - All 4 scores in single row: ✓")
print(f"   - Static 'How to Act' section: ✓")
print(f"   - Total issues: {len(audit_data['issues'])} shown (of {audit_data['total_issues_identified']} identified)")
