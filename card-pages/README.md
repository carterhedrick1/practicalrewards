# Card Pages Design System

This document explains the standardized design structure for all individual card pages, featuring a modern hero section, practical recommendations, and an interactive calculator.

## Overview

Each card page follows a consistent structure with these main sections:

1. **Hero Section** - Card image, key info, and visual appeal
2. **Practical Recommendation** - Who the card is best for
3. **Perks & Protections** - Key benefits and protections
4. **Effective Annual Fee Calculator** - Interactive credit calculator
5. **Navigation** - Links to other cards

## Structure

### Hero Section

The hero section features a two-column layout with the card image on the left and key information on the right.

```html
<div class="hero-section">
    <div class="hero-content">
        <div class="hero-text">
            <h1>CARD NAME</h1>
            <p class="hero-subtitle">CARD SUBTITLE</p>
            <div class="hero-card-container">
                <div class="hero-card">
                    <img src="../../images/CARD-IMAGE.jpg" alt="CARD NAME" class="hero-card-image">
                    <!-- Fallback card preview -->
                </div>
            </div>
        </div>
        <div class="hero-info">
            <div class="info-section">
                <div class="info-row">
                    <span class="info-label">Annual Fee</span>
                    <span class="info-value">$XXX</span>
                </div>
                <div class="info-row">
                    <span class="info-label">Earning Rate</span>
                    <span class="info-value">Xx points on category</span>
                </div>
                <div class="info-row">
                    <span class="info-label">Perks</span>
                    <span class="info-value">Key perk 1, key perk 2</span>
                </div>
                <div class="info-row">
                    <span class="info-label">Protections</span>
                    <span class="info-value">Key protection 1, key protection 2</span>
                </div>
                <div class="info-row">
                    <span class="info-label">Welcome Bonus</span>
                    <span class="info-value">XX,XXX points after $X,XXX spend in X months</span>
                </div>
                <div class="info-row">
                    <span class="info-label">Card Material</span>
                    <span class="info-value">Metal card with premium finish</span>
                </div>
            </div>
        </div>
    </div>
</div>
```

### Practical Recommendation Section

Provides clear guidance on who should get the card.

```html
<div class="recommendation-section">
    <div class="recommendation-content">
        <h2>Practical Recommendation</h2>
        <div class="recommendation-text">
            <p>The <strong>CARD NAME</strong> is best suited for [target audience]. With a $XXX annual fee, this card makes financial sense if you:</p>
            <ul class="recommendation-list">
                <li><strong>Criteria 1</strong> - explanation</li>
                <li><strong>Criteria 2</strong> - explanation</li>
                <li><strong>Criteria 3</strong> - explanation</li>
                <li><strong>Criteria 4</strong> - explanation</li>
            </ul>
        </div>
    </div>
</div>
```

### Perks & Protections Wrapper

Two-column layout showing key benefits and protections.

```html
<div class="perks-protections-wrapper">
    <!-- PERKS SECTION -->
    <div class="recommendation-section perks-section">
        <div class="recommendation-content">
            <h2>Perks</h2>
            <div class="recommendation-text">
                <p>Key benefits and access with the CARD NAME:</p>
                <ul class="recommendation-list">
                    <li>Perk 1</li>
                    <li>Perk 2</li>
                    <li>Perk 3</li>
                    <li>Perk 4</li>
                    <li>Perk 5</li>
                </ul>
            </div>
        </div>
    </div>

    <!-- PROTECTIONS SECTION -->
    <div class="recommendation-section protections-section">
        <div class="recommendation-content">
            <h2>Protections</h2>
            <div class="recommendation-text">
                <p>Insurance and security features included:</p>
                <ul class="recommendation-list">
                    <li>Protection 1</li>
                    <li>Protection 2</li>
                    <li>Protection 3</li>
                    <li>Protection 4</li>
                    <li>Protection 5</li>
                </ul>
            </div>
        </div>
    </div>
</div>
```

### Effective Annual Fee Calculator

Interactive calculator with collapsible sections and modern table design.

```html
<div class="calculator-section collapsible-section">
    <div class="section-container">
        <div class="calculator-header" id="calculator-header" role="button" tabindex="0" aria-expanded="true" aria-controls="calculator-content" onclick="toggleCalculatorSection()" onkeydown="handleKeyToggle(event)">
            <div class="section-header-content">
                <h2>Effective Annual Fee Calculator</h2>
                <p>Calculate your real cost after credits. Select the credits you'll actually use to see your real annual cost. Only count credits for services you'd pay for anyway.</p>
            </div>
            <div class="section-toggle-icon" aria-hidden="true">
                <!-- SVG toggle icon -->
            </div>
        </div>
    
        <div class="calculator-content" id="calculator-content" role="region" aria-labelledby="calculator-header">
            <div class="calculator-table">
                <div class="table-header">
                    <div class="header-credit">Credit</div>
                    <div class="header-toggle">Include</div>
                    <div class="header-value">Your Value</div>
                </div>
                
                <!-- Credit rows -->
                <div class="table-row">
                    <div class="credit-info">
                        <div class="credit-name">Credit Name</div>
                        <div class="credit-description">Description of the credit and any important notes about usage.</div>
                    </div>
                    <div class="toggle-container">
                        <label class="credit-toggle">
                            <input type="checkbox" onchange="toggleCredit(this)" data-max="XXX">
                            <span class="toggle-slider"></span>
                        </label>
                    </div>
                    <div class="value-column">
                        <div class="value-input" style="display: none !important;">
                            <span class="currency">$</span>
                            <input type="number" value="0" min="0" max="XXX" onchange="syncInputValues(this)" data-max="XXX">
                        </div>
                        <div class="value-placeholder" style="display: block !important;">$0</div>
                    </div>
                    <!-- Mobile controls -->
                    <div class="mobile-controls-table">
                        <!-- Mobile version of controls -->
                    </div>
                </div>
            </div>

            <div class="calculator-results">
                <div class="result-row">
                    <span class="result-label">Total Credits:</span>
                    <span class="result-value">$<span id="total-credits">0</span></span>
                </div>
                <div class="result-row">
                    <span class="result-label">Effective Annual Fee:</span>
                    <span class="result-value" id="effective-fee">$XXX</span>
                </div>
            </div>
        </div>
    </div>
</div>
```

## Adding New Cards

### Quick Start Process

1. **Copy the template**: Use `card-template.html` as your starting point
2. **Update basic info**: Title, card name, subtitle, image path
3. **Fill hero info**: Annual fee, earning rate, perks, protections, welcome bonus, card material
4. **Write recommendation**: Who should get this card and why
5. **List perks & protections**: Key benefits and insurance features
6. **Add credits**: Use the table-row structure for each credit
7. **Set annual fee**: Update the JavaScript variable
8. **Update navigation**: Link to relevant comparison cards

### Required Information for Each Card

#### Hero Section
- **Card Name**: Full official name
- **Subtitle**: Brief description (e.g., "Chase's Top-Tier Travel Card")
- **Image**: High-quality card image (320x200px recommended)
- **Annual Fee**: Exact dollar amount
- **Earning Rate**: Main earning category (e.g., "3x points on travel & dining")
- **Welcome Bonus**: Current offer with spend requirement
- **Card Material**: Physical card description

#### Practical Recommendation
- **Target Audience**: Who the card is best for
- **Criteria**: 4 specific conditions that make the card worthwhile
- **Realistic Assessment**: Honest evaluation of value proposition

#### Credits Calculator
- **Credit Name**: Clear, descriptive name
- **Description**: Detailed explanation with usage notes
- **Maximum Value**: Set in data-max attribute
- **Realistic Notes**: Include limitations and usage requirements

## Styling & Responsiveness

### Desktop Layout
- Hero section: Two-column grid
- Perks & Protections: Side-by-side layout
- Calculator: Full-width table with three columns

### Mobile Layout
- Hero section: Single column, card image first
- Perks & Protections: Stacked vertically
- Calculator: Mobile-optimized controls with labels

### Interactive Elements
- Calculator toggle: Collapsible section with smooth animation
- Credit toggles: Modern switch design with value inputs
- Mobile menu: Responsive navigation
- Hover effects: Subtle animations and transitions

## Shared Files

### CSS (`card-styles.css`)
- All styling for card pages
- Responsive breakpoints
- Interactive animations
- Modern design system

### JavaScript (`card-scripts.js`)
- Calculator functionality
- Mobile menu handling
- Header/footer loading
- Form interactions

### Template (`card-template.html`)
- Complete starting point for new cards
- All required sections and structure
- Detailed usage instructions
- Placeholder content to replace

## Benefits

This standardized approach provides:

- **Consistency**: All cards follow the same design pattern
- **User Experience**: Intuitive navigation and interaction
- **Comparability**: Easy to compare cards side-by-side
- **Scalability**: Quick creation of new card pages
- **Maintainability**: Centralized styling and functionality
- **Accessibility**: ARIA labels and keyboard navigation
- **Performance**: Optimized loading and interactions

## Example Implementations

### Venture X
- **Hero**: Capital One branding with metal card image
- **Recommendation**: Focus on travel frequency and credit usage
- **Calculator**: 3 main credits with realistic descriptions
- **Navigation**: Links to Sapphire Reserve and Amex Platinum

### Sapphire Reserve
- **Hero**: Chase branding with premium positioning
- **Recommendation**: Emphasizes travel and dining spend
- **Calculator**: 10+ credits with detailed usage notes
- **Navigation**: Links to Amex Platinum and Venture X

### Amex Platinum
- **Hero**: Luxury positioning with comprehensive benefits
- **Recommendation**: Targets frequent travelers and luxury consumers
- **Calculator**: 6 main credits with clear limitations
- **Navigation**: Links to Venture X and Sapphire Reserve

## Future Enhancements

Potential improvements to consider:

- **Comparison Mode**: Side-by-side card comparison
- **Credit Tracking**: Save user preferences
- **Dynamic Pricing**: Real-time credit value updates
- **Personalization**: Tailored recommendations
- **Analytics**: Track user interactions and preferences
- **A/B Testing**: Test different layouts and content 