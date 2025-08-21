#!/usr/bin/env node

/**
 * Card Page Generator
 * 
 * This script helps you quickly create new card pages from the template.
 * Usage: node create-card.js "Card Name" "card-filename"
 * 
 * Example: node create-card.js "Chase Freedom Unlimited" "chase-freedom-unlimited"
 */

const fs = require('fs');
const path = require('path');

// Get command line arguments
const args = process.argv.slice(2);

if (args.length < 2) {
    console.log(`
Card Page Generator

Usage: node create-card.js "Card Name" "filename"

Examples:
  node create-card.js "Chase Freedom Unlimited" "chase-freedom-unlimited"
  node create-card.js "Amex Gold" "amex-gold"
  node create-card.js "Capital One Savor" "capital-one-savor"

The script will:
1. Copy card-template.html to your new filename
2. Replace placeholder text with your card name
3. Create a basic structure ready for customization
4. Include performance optimizations and SEO features
`);
    process.exit(1);
}

const cardName = args[0];
const filename = args[1];
const outputFile = `${filename}.html`;

// Read the template
const templatePath = path.join(__dirname, 'card-template.html');
const template = fs.readFileSync(templatePath, 'utf8');

// Replace placeholders
let newContent = template
    .replace(/CARD NAME/g, cardName)
    .replace(/CARD SUBTITLE/g, `${cardName} - Credit Card Review`)
    .replace(/CARD-IMAGE\.jpg/g, `${filename}.jpg`)
    .replace(/CARD-FILENAME\.html/g, outputFile)
    .replace(/BANK NAME/g, getBankName(cardName))
    .replace(/card-template\.html/g, outputFile)
    .replace(/CARD NAME DEBUG/g, `${cardName.toUpperCase().replace(/\s+/g, '_')} DEBUG`)
    .replace(/Apply for CARD NAME/g, `Apply for ${cardName}`);

// Update the annual fee placeholder
newContent = newContent.replace(/const annualFee = XXX;/, 'const annualFee = 0; // TODO: Update with actual annual fee');

// Write the new file
const outputPath = path.join(__dirname, outputFile);
fs.writeFileSync(outputPath, newContent);

console.log(`
✅ Card page created successfully!

File: ${outputFile}
Card: ${cardName}

Next steps:
1. Add your card image to the images/ folder as "${filename}.jpg"
2. Update the hero info section with card details
3. Write the practical recommendation
4. Add perks and protections
5. Configure the credits calculator
6. Update the annual fee variable
7. Set up navigation links

Performance optimizations included:
✅ Resource preloading
✅ Lazy image loading
✅ Cache-busting versions
✅ SEO meta tags
✅ Structured data
✅ Performance monitoring

Template usage instructions are included in the file comments.
`);

function getBankName(cardName) {
    const lowerName = cardName.toLowerCase();
    
    if (lowerName.includes('chase') || lowerName.includes('sapphire') || lowerName.includes('freedom')) {
        return 'Chase';
    } else if (lowerName.includes('amex') || lowerName.includes('american express') || lowerName.includes('platinum') || lowerName.includes('gold')) {
        return 'American Express';
    } else if (lowerName.includes('capital one') || lowerName.includes('venture')) {
        return 'Capital One';
    } else if (lowerName.includes('citi') || lowerName.includes('prestige') || lowerName.includes('premier')) {
        return 'Citi';
    } else if (lowerName.includes('bofa') || lowerName.includes('bank of america')) {
        return 'Bank of America';
    } else if (lowerName.includes('wells fargo')) {
        return 'Wells Fargo';
    } else {
        return 'BANK NAME'; // Keep placeholder if unknown
    }
} 