# Cards for Normals - Credit Card Management System

## Overview

This project has been transformed from an Annual Fee Calculator to a comprehensive Credit Cards product grid system with admin management capabilities.

## New Structure

### Main Pages
- **`cards.html`** - The main Cards page (formerly `eaacalc.html`)
- **`admin-cards.html`** - Admin interface for managing credit cards

### Key Features

#### Cards Page (`cards.html`)
- **Product Grid**: Displays credit cards in an e-commerce style layout
- **Advanced Filtering**: Filter by card type, annual fee, credit score, and rewards
- **Sorting**: Sort by name, fee, or featured order
- **Responsive Design**: Works on desktop and mobile devices
- **Dynamic Loading**: Cards are loaded from the admin system

#### Admin Page (`admin-cards.html`)
- **Card Management**: Add, edit, and delete credit cards
- **Data Export/Import**: JSON export/import functionality
- **Status Management**: Set cards as active, draft, or inactive
- **Rich Form Fields**: Comprehensive card information including features, tags, and URLs

## How to Use

### For Users
1. Visit `cards.html` to browse credit cards
2. Use the filter buttons to narrow down your search
3. Click on any card to view details or visit the card's page
4. Use the sort dropdown to organize cards by different criteria

### For Administrators
1. Visit `admin-cards.html` to manage the card database
2. Click "Add New Card" to create new entries
3. Use the table to view, edit, or delete existing cards
4. Export data for backup or import from other sources
5. Set card status to control visibility on the main page

## Technical Details

### Data Storage
- Cards are stored in browser localStorage for persistence
- Admin changes are immediately reflected on the cards page
- Fallback data is provided if no admin data exists

### Card Data Structure
Each card includes:
- Basic info (name, type, annual fee, bank type)
- Rewards type (points, miles, cashback, hybrid)
- Features list
- Feature categories (lounge access, TSA PreCheck, travel insurance, etc.)
- Image URL and card page URL
- Status (active/draft/inactive)

### Integration
- The cards page automatically loads data from the admin system
- Changes made in admin are visible after refreshing the cards page
- All existing card pages (venture-x.html, sapphire-reserve.html, etc.) remain functional

## Navigation Updates

All navigation throughout the site has been updated:
- Header navigation now shows "Cards" instead of "Calculator"
- Footer links updated accordingly
- Card page back buttons now link to "Cards" instead of "Card Selection"
- All internal references updated to use `cards.html`

## Getting Started

1. **View Cards**: Navigate to `cards.html`
2. **Manage Cards**: Navigate to `admin-cards.html`
3. **Add Sample Data**: Use the admin page to add your first cards
4. **Customize**: Modify the filter categories and card fields as needed

## Browser Compatibility

- Modern browsers with localStorage support
- Responsive design for mobile and desktop
- No external dependencies required

## Future Enhancements

- Backend database integration
- User accounts and favorites
- Advanced analytics and reporting
- API endpoints for external integrations
- Enhanced search and recommendation algorithms 