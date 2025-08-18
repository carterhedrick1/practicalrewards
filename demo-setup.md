# Demo Setup Guide

## Quick Start Demo

### 1. Start the Server
```bash
python3 -m http.server 8021
```

### 2. Test the System

#### Step 1: View the Cards Page
- Navigate to: `http://localhost:8021/cards.html`
- You should see the default cards (Venture X, Sapphire Reserve, Amex Platinum)
- Test the filters and sorting functionality

#### Step 2: Access the Admin Panel
- Navigate to: `http://localhost:8021/admin-cards.html`
- You'll see the current cards in a table format
- Click "Add New Card" to test the form

#### Step 3: Add a New Card
1. Click "Add New Card" button
2. Fill out the form with sample data:
   - **Name**: "Chase Freedom Unlimited"
   - **Type**: "cashback"
   - **Annual Fee**: "0"
   - **Credit Score**: "good"
   - **Rewards**: "cashback"
   - **Features**: Add 3-4 features (one per line)
   - **Tags**: Add tags like "No Annual Fee", "Cashback"
3. Click "Save Card"

#### Step 4: See Changes on Cards Page
1. Go back to `http://localhost:8021/cards.html`
2. Click the "Refresh" button
3. Your new card should appear in the grid
4. Test filtering by "No Annual Fee" to see it

#### Step 5: Test Admin Features
1. Go back to admin panel
2. Try editing an existing card
3. Test the export/import functionality
4. Change card status between active/draft/inactive

### 3. Test Filtering

#### Filter by Annual Fee
- Click "No Annual Fee" filter
- Should show only cards with $0 annual fee

#### Filter by Card Type
- Click "Travel" filter
- Should show only travel cards

#### Filter by Bank Type
- Click "Bank Cards" filter
- Should show only traditional bank cards

#### Filter by Features
- Click "Lounge Access" filter
- Should show only cards with lounge access

### 4. Test Sorting

- Use the sort dropdown to test different sorting options
- "Fee: Low to High" should organize cards by annual fee
- "Name A-Z" should alphabetize cards

### 5. Test Responsiveness

- Resize your browser window to test mobile responsiveness
- The filter buttons should stack vertically on small screens
- Cards should reflow to single column on mobile

## Expected Results

### Default Cards
- **Capital One Venture X**: $395, Travel, Miles
- **Chase Sapphire Reserve**: $795, Travel, Points  
- **American Express Platinum**: $695, Travel, Points

### After Adding Sample Card
- **Chase Freedom Unlimited**: $0, Cashback, Cashback

## Troubleshooting

### Cards Not Loading
- Check browser console for JavaScript errors
- Ensure localStorage is enabled in your browser
- Try refreshing the page

### Admin Changes Not Visible
- Click the "Refresh" button on the cards page
- Check that cards are set to "active" status in admin

### Filter Not Working
- Ensure you've clicked the filter button (should turn green)
- Check that card data has the correct filter values

## Next Steps

1. **Customize Filters**: Modify filter categories in `cards.html`
2. **Add More Cards**: Use admin panel to populate with real card data
3. **Customize Styling**: Modify CSS in both files to match your brand
4. **Add Features**: Enhance with ratings, reviews, or comparison tools
5. **Backend Integration**: Replace localStorage with a real database

## Browser Compatibility

- **Chrome/Edge**: Full support
- **Firefox**: Full support  
- **Safari**: Full support
- **Mobile Browsers**: Responsive design works on all modern mobile browsers 