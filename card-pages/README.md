# Card Pages Features System

This document explains how to use the standardized features section that has been added to all individual card pages.

## Overview

The features section provides a consistent, comparable format for displaying key card information across all pages. It includes three main sections:

1. **💳 Earning Rates** - How the card earns points/miles
2. **🎁 Perks & Benefits** - Luxury benefits and exclusive access
3. **🛡️ Protections** - Insurance and security features

## Structure

The features section is placed between the hero section and the callout box on every card page. It uses a responsive grid layout that automatically adjusts based on screen size.

### HTML Structure

```html
<!-- FEATURES SECTION - Standardized format for all cards -->
<div class="features-section">
    <div class="features-grid">
        <!-- EARNING RATE SECTION -->
        <div class="feature-card earning-rates">
            <div class="feature-header">
                <h3>💳 Earning Rates</h3>
                <p class="feature-subtitle">How you earn [POINT_TYPE]</p>
            </div>
            <div class="earning-categories">
                <div class="earning-category">
                    <div class="category-name">Category Name</div>
                    <div class="earning-rate">Xx points</div>
                </div>
                <!-- Add more categories as needed -->
            </div>
        </div>

        <!-- PERKS SECTION -->
        <div class="feature-card perks">
            <div class="feature-header">
                <h3>🎁 Perks & Benefits</h3>
                <p class="feature-subtitle">Luxury benefits and exclusive access</p>
            </div>
            <div class="perks-list">
                <div class="perk-item">
                    <span class="perk-icon">✈️</span>
                    <span class="perk-text">Perk description</span>
                </div>
                <!-- Add more perks as needed -->
            </div>
        </div>

        <!-- PROTECTIONS SECTION -->
        <div class="feature-card protections">
            <div class="feature-header">
                <h3>🛡️ Protections</h3>
                <p class="feature-subtitle">Insurance and security features</p>
            </div>
            <div class="protections-list">
                <div class="protection-item">
                    <span class="protection-icon">🛡️</span>
                    <span class="protection-text">Protection description</span>
                </div>
                <!-- Add more protections as needed -->
            </div>
        </div>
    </div>
</div>
```

## Customization Guidelines

### Earning Rates Section

- **Subtitle**: Change to reflect the specific point/mile system (e.g., "How you earn Membership Rewards points")
- **Categories**: List the main earning categories with their multipliers
- **Format**: Use consistent formatting like "Xx points" or "Xx miles"
- **Order**: List highest earning rate first, then descending

### Perks Section

- **Subtitle**: Usually keep as "Luxury benefits and exclusive access"
- **Icons**: Use relevant emojis for each perk (✈️ for travel, 🏨 for hotels, etc.)
- **Content**: Focus on premium benefits that differentiate the card
- **Quantity**: Aim for 4-6 key perks to maintain visual balance

### Protections Section

- **Subtitle**: Usually keep as "Insurance and security features"
- **Icons**: Use relevant emojis for each protection type
- **Content**: List the main insurance and security features
- **Quantity**: Aim for 4-6 key protections

## Adding New Cards

When creating a new card page:

1. **Copy the template**: Use `card-template.html` as your starting point
2. **Update the features section**: Replace the placeholder content with card-specific information
3. **Maintain consistency**: Keep the same structure and styling
4. **Test responsiveness**: Ensure the grid works well on mobile devices

## Styling

The features section uses CSS Grid with responsive breakpoints:

- **Desktop**: 3-column grid
- **Tablet**: 2-column grid (when space allows)
- **Mobile**: Single-column stack

All styling is handled in `card-styles.css` and automatically applies to new pages.

## Benefits

This standardized approach provides:

- **Consistency**: All cards look and feel the same
- **Comparability**: Users can easily compare features across cards
- **Scalability**: Easy to add new cards with minimal effort
- **Maintainability**: Changes to styling affect all pages automatically
- **SEO**: Structured content that search engines can understand

## Example Customizations

### Amex Platinum
- **Earning**: 5x on flights/hotels, 1x on everything else
- **Perks**: Centurion lounges, Fine Hotels & Resorts, concierge
- **Protections**: Extended warranty, trip cancellation, car rental

### Chase Sapphire Reserve
- **Earning**: 3x on travel/dining, 1x on everything else
- **Perks**: Priority Pass, The Edit hotels, Exclusive Tables
- **Protections**: Extended warranty, trip delay, primary car rental

### Capital One Venture X
- **Earning**: 2x on everything, 5x on Capital One Travel
- **Perks**: Priority Pass, Capital One lounges, concierge
- **Protections**: Extended warranty, trip cancellation, car rental

## Future Enhancements

Potential improvements to consider:

- **Interactive elements**: Click to expand detailed descriptions
- **Comparison mode**: Side-by-side feature comparison
- **Filtering**: Show/hide specific feature types
- **Search**: Find cards by specific features
- **Data export**: Generate comparison reports 