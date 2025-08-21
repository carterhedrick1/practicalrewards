# Quick Start Guide - Creating New Card Pages

## 🚀 Fast Setup

### Option 1: Use the Generator Script (Recommended)
```bash
cd card-pages
node create-card.js "Card Name" "filename"
```

**Examples:**
```bash
node create-card.js "Chase Freedom Unlimited" "chase-freedom-unlimited"
node create-card.js "Amex Gold" "amex-gold"
node create-card.js "Capital One Savor" "capital-one-savor"
```

### Option 2: Manual Copy
1. Copy `card-template.html`
2. Rename to `your-card-name.html`
3. Follow the template instructions

## 📋 What You Need to Update

### 1. Basic Info (5 minutes)
- **Title**: Page title in `<title>` tag
- **Card Name**: Main heading and throughout page
- **Subtitle**: Brief description under card name
- **Image**: Add card image to `images/` folder

### 2. Hero Section (10 minutes)
Update the 4 info rows:
- **Annual Fee**: Exact dollar amount
- **Earning Rate**: Main earning category
- **Welcome Bonus**: Current offer with spend requirement
- **Card Material**: Physical card description

### 3. Practical Recommendation (15 minutes)
- **Target Audience**: Who should get this card
- **4 Criteria**: Specific conditions that make it worthwhile
- **Realistic Assessment**: Honest value proposition

### 4. Perks & Protections (10 minutes)
- **Perks**: 4-6 key benefits
- **Protections**: 4-6 insurance features
- Keep descriptions concise and clear

### 5. Credits Calculator (20 minutes)
For each credit, add a `table-row` with:
- **Credit Name**: Clear, descriptive name
- **Description**: Detailed explanation with usage notes
- **Maximum Value**: Set in `data-max` attribute
- **Realistic Notes**: Include limitations and requirements

### 6. Final Setup (5 minutes)
- **Annual Fee**: Update JavaScript variable
- **Apply Button**: Update href with actual application link
- **Test**: Check mobile responsiveness

## 🎯 Example: Chase Freedom Unlimited

### Hero Info
```
Annual Fee: $0
Earning Rate: 5% on rotating categories, 1.5% on everything
Welcome Bonus: $200 after $500 spend in 3 months
Card Material: Plastic card
```

### Practical Recommendation
```
The Chase Freedom Unlimited is best suited for everyday spenders who want simple rewards. With no annual fee, this card makes financial sense if you:

• Want a simple, no-fee rewards card
• Can maximize the 5% rotating categories
• Value the 0% intro APR offer
• Are building credit or new to rewards
```

### Credits Calculator
```
Credit Name: No Annual Fee
Description: This card has no annual fee, so no credits to calculate.
Maximum Value: 0
```

## 📱 Mobile Testing

After creating your page:
1. Open in browser
2. Test mobile menu
3. Check calculator responsiveness
4. Verify all links work
5. Test credit toggles

## 🔧 Troubleshooting

### Calculator Not Working
- Check `annualFee` variable is set
- Verify all `data-max` attributes are numbers
- Ensure `card-scripts.js` is loaded

### Mobile Menu Issues
- Check header loads correctly
- Verify `setupMobileMenu` function exists
- Test on actual mobile device

### Styling Problems
- All styles are in `card-styles.css`
- Check for typos in class names
- Verify CSS file is linked correctly

## 📚 Resources

- **Template**: `card-template.html` - Complete starting point
- **Styles**: `card-styles.css` - All styling and responsive design
- **Scripts**: `card-scripts.js` - Calculator and mobile functionality
- **Documentation**: `README.md` - Detailed design system guide

## ⚡ Pro Tips

1. **Start with the template** - It has everything you need
2. **Use realistic credit values** - Don't overestimate usage
3. **Test on mobile** - Most users are on mobile
4. **Keep descriptions honest** - Build trust with realistic assessments
5. **Link to relevant cards** - Help users compare options

## 🎉 You're Ready!

Your card pages now have:
- ✅ Modern hero section with card image
- ✅ Practical recommendations
- ✅ Interactive credit calculator
- ✅ Mobile-responsive design
- ✅ Consistent styling across all cards
- ✅ Easy template for new cards

Happy card creating! 🚀 