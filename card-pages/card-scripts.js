// Shared Card Page Scripts - Update this file to change all card pages

// Load header and footer
document.addEventListener('DOMContentLoaded', function() {
    loadComponent('../../header.html', 'header-placeholder', 'header-fallback');
    loadComponent('../../footer.html', 'footer-placeholder', 'footer-fallback');
    
    // Initialize calculator placeholders when page loads
    initializeCalculatorPlaceholders();
});

function loadComponent(filename, placeholderId, fallbackId) {
    const placeholder = document.getElementById(placeholderId);
    
    fetch(filename)
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            return response.text();
        })
        .then(html => {
            placeholder.innerHTML = html;
            initializeLoadedContent();
        })
        .catch(error => {
            console.warn(`Could not load ${filename}:`, error);
            placeholder.innerHTML = getFallbackContent(filename);
        });
}

function getFallbackContent(filename) {
    if (filename === '../../header.html') {
        return `
            <header style="background: rgba(250, 250, 249, 0.95); backdrop-filter: blur(12px); box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.1), 0 1px 2px 0 rgba(0, 0, 0, 0.06); position: sticky; top: 0; z-index: 1000; width: 100%; border-bottom: 1px solid #e7e5e4;">
                <nav style="max-width: 1400px; margin: 0 auto; padding: 0 2rem; display: flex; justify-content: space-between; align-items: center; height: 80px;">
                    <a href="#" class="logo" style="font-size: 1.5rem; font-weight: 700; color: #059669; text-decoration: none;">Practical Rewards</a>
                    <ul style="display: flex; list-style: none; gap: 2rem; margin: 0; padding: 0;">
                        <li><a href="#" style="color: #57534e; text-decoration: none; font-weight: 500;">Home</a></li>
                        <li><a href="#" style="color: #57534e; text-decoration: none; font-weight: 500;">Learning</a></li>
                        <li><a href="#" style="color: #57534e; text-decoration: none; font-weight: 500;">Calculator</a></li>
                        <li><a href="#" style="color: #57534e; text-decoration: none; font-weight: 500;">About</a></li>
                    </ul>
                </nav>
            </header>
            <script>
            // Simple absolute path navigation that works from anywhere
            (function() {
                function updateNavigationPaths() {
                    // Get the current domain and protocol
                    const protocol = window.location.protocol;
                    const host = window.location.host;
                    const baseUrl = protocol + '//' + host;
                    
                    // Update all navigation links to use absolute paths from root
                    const navLinks = document.querySelectorAll('a[href="#"]');
                    
                    navLinks.forEach((link, index) => {
                        const pages = ['index.html', 'learning.html', 'eaacalc.html', 'about.html'];
                        if (index < pages.length) {
                            // Create absolute URL from root - this will work from any page depth
                            link.href = baseUrl + '/' + pages[index];
                        }
                    });
                }
                
                // Run immediately and also when DOM is ready
                updateNavigationPaths();
                
                if (document.readyState === 'loading') {
                    document.addEventListener('DOMContentLoaded', updateNavigationPaths);
                }
                
                // Also run after a short delay to catch any late-loading elements
                setTimeout(updateNavigationPaths, 50);
            })();
            </script>
        `;
    } else if (filename === '../../footer.html') {
        return `
            <footer style="background: #292524; color: #a8a29e; padding: 3rem 0 1rem 0; margin-top: 3rem;">
                <div style="max-width: 1400px; margin: 0 auto; padding: 0 2rem;">
                    <div style="text-align: center;">
                        <p>&copy; 2025 Cards for Normals. All rights reserved.</p>
                        <p style="margin-top: 1rem;">
                            <a href="#" style="color: #a8a29e; text-decoration: none; margin: 0 1rem;">Learning</a>
                            <a href="#" style="color: #a8a29e; text-decoration: none; margin: 0 1rem;">Calculator</a>
                            <a href="#" style="color: #a8a29e; text-decoration: none; margin: 0 1rem;">About</a>
                        </p>
                    </div>
                </div>
            </footer>
        `;
    }
    return '<p>Content could not be loaded.</p>';
}

function initializeLoadedContent() {
    const header = document.querySelector('header');
    if (header) {
        window.addEventListener('scroll', () => {
            if (window.scrollY > 100) {
                header.style.background = 'rgba(250, 250, 249, 0.98)';
                header.style.boxShadow = '0 4px 20px rgba(0, 0, 0, 0.1)';
            } else {
                header.style.background = 'rgba(250, 250, 249, 0.95)';
                header.style.boxShadow = 'none';
            }
        });
    }
}

// Collapsible section functionality
function toggleSection(sectionId) {
    const sectionContent = document.getElementById(sectionId);
    const sectionHeader = sectionContent.previousElementSibling;
    const toggleIcon = sectionHeader.querySelector('.toggle-icon');
    
    if (sectionContent.classList.contains('collapsed')) {
        // Expand section
        sectionContent.classList.remove('collapsed');
        sectionHeader.classList.remove('collapsed');
        toggleIcon.textContent = '−';
    } else {
        // Collapse section
        sectionContent.classList.add('collapsed');
        sectionHeader.classList.add('collapsed');
        toggleIcon.textContent = '+';
    }
}

// Initialize collapsible sections when page loads
document.addEventListener('DOMContentLoaded', function() {
    // Add click event listeners to all section headers
    const sectionHeaders = document.querySelectorAll('.section-header');
    sectionHeaders.forEach(header => {
        header.addEventListener('click', function() {
            const sectionId = this.nextElementSibling.id;
            toggleSection(sectionId);
        });
    });
    
    // Initialize calculator section
    initializeCalculatorSection();
}); 

// Initialize calculator placeholders to show $0 when toggles are off
function initializeCalculatorPlaceholders() {
    console.log('Initializing calculator placeholders...');
    const checkboxes = document.querySelectorAll('input[type="checkbox"]');
    console.log('Found checkboxes:', checkboxes.length);
    
    checkboxes.forEach(checkbox => {
        const creditItem = checkbox.closest('.table-row');
        const placeholder = creditItem.querySelector('.value-placeholder');
        const valueInput = creditItem.querySelector('.value-input');
        
        console.log('Credit item:', creditItem);
        console.log('Placeholder:', placeholder);
        console.log('Value input:', valueInput);
        
        if (placeholder && valueInput) {
            if (!checkbox.checked) {
                placeholder.style.setProperty('display', 'block', 'important');
                placeholder.textContent = '$0';
                valueInput.style.setProperty('display', 'none', 'important');
                valueInput.classList.remove('active');
                // Ensure mobile placeholders have consistent styling
                if (placeholder.closest('.mobile-controls-table')) {
                    placeholder.style.setProperty('color', '#9ca3af', 'important');
                    placeholder.style.setProperty('background', 'transparent', 'important');
                    placeholder.style.setProperty('border', 'none', 'important');
                    placeholder.style.setProperty('box-shadow', 'none', 'important');
                }
                console.log('Set placeholder visible for unchecked checkbox');
            } else {
                placeholder.style.setProperty('display', 'none', 'important');
                valueInput.style.setProperty('display', 'flex', 'important');
                valueInput.classList.add('active');
                console.log('Set input visible for checked checkbox');
            }
        }
    });
}

// Toggle credit function - sets input to max value when toggled on
function toggleCredit(checkbox) {
    console.log('Toggle credit called for:', checkbox);
    const creditItem = checkbox.closest('.table-row');
    const maxValue = parseInt(checkbox.getAttribute('data-max'));
    
    // Find ALL related controls in this credit item (both desktop and mobile)
    const allInputFields = creditItem.querySelectorAll('input[type="number"]');
    const allValueInputs = creditItem.querySelectorAll('.value-input');
    const allPlaceholders = creditItem.querySelectorAll('.value-placeholder');
    const allCheckboxes = creditItem.querySelectorAll('input[type="checkbox"]');
    
    console.log('Credit item:', creditItem);
    console.log('All input fields:', allInputFields.length);
    console.log('All value inputs:', allValueInputs.length);
    console.log('All placeholders:', allPlaceholders.length);
    console.log('All checkboxes:', allCheckboxes.length);
    console.log('Max value:', maxValue);
    console.log('Checkbox checked:', checkbox.checked);
    
    // Synchronize all checkboxes in this credit item
    allCheckboxes.forEach(cb => {
        cb.checked = checkbox.checked;
    });
    
    if (checkbox.checked) {
        // Toggle ON - show input field, hide placeholder for ALL controls
        allInputFields.forEach(inputField => {
            inputField.value = maxValue;
        });
        allValueInputs.forEach(valueInput => {
            valueInput.style.setProperty('display', 'flex', 'important');
            // Add active class for animation after a short delay
            setTimeout(() => {
                valueInput.classList.add('active');
            }, 10);
        });
        allPlaceholders.forEach(placeholder => {
            placeholder.style.setProperty('display', 'none', 'important');
        });
        console.log('Turned ON - showing inputs, hiding placeholders');
    } else {
        // Toggle OFF - hide input field, show placeholder for ALL controls
        allInputFields.forEach(inputField => {
            inputField.value = 0;
        });
        allValueInputs.forEach(valueInput => {
            valueInput.classList.remove('active');
            // Hide after animation completes
            setTimeout(() => {
                valueInput.style.setProperty('display', 'none', 'important');
            }, 300);
        });
        allPlaceholders.forEach(placeholder => {
            placeholder.style.setProperty('display', 'block', 'important');
            placeholder.textContent = '$0';
            // Ensure mobile placeholders have consistent styling
            if (placeholder.closest('.mobile-controls-table')) {
                placeholder.style.setProperty('color', '#9ca3af', 'important');
                placeholder.style.setProperty('background', 'transparent', 'important');
                placeholder.style.setProperty('border', 'none', 'important');
                placeholder.style.setProperty('box-shadow', 'none', 'important');
            }
        });
        console.log('Turned OFF - hiding inputs, showing placeholders');
    }
    
    updateCalculation();
}

// Function to sync input values between desktop and mobile when manually changed
function syncInputValues(inputField) {
    const creditItem = inputField.closest('.table-row');
    const allInputFields = creditItem.querySelectorAll('input[type="number"]');
    
    // Sync all input fields in this credit item
    allInputFields.forEach(field => {
        if (field !== inputField) {
            field.value = inputField.value;
        }
    });
    
    updateCalculation();
}

// Debug function to force show all placeholders
function forceShowPlaceholders() {
    console.log('Force showing all placeholders...');
    const placeholders = document.querySelectorAll('.value-placeholder');
    const valueInputs = document.querySelectorAll('.value-input');
    
    console.log('Found placeholders:', placeholders.length);
    console.log('Found value inputs:', valueInputs.length);
    
    placeholders.forEach((placeholder, index) => {
        placeholder.style.display = 'block';
        placeholder.style.color = 'red';
        placeholder.style.border = '2px solid red';
        placeholder.textContent = '$0';
        console.log(`Placeholder ${index}:`, placeholder);
    });
    
    valueInputs.forEach((input, index) => {
        input.style.display = 'none';
        console.log(`Value input ${index}:`, input);
    });
}

// Generic calculator functionality - each page should define its own annualFee variable
function updateCalculation() {
    if (typeof annualFee === 'undefined') {
        console.warn('annualFee not defined on this page');
        return;
    }
    
    // Get unique credit items to avoid double counting
    const creditItems = document.querySelectorAll('.table-row');
    
    let totalCredits = 0;
    creditItems.forEach(creditItem => {
        // Check if any checkbox in this credit item is checked
        const checkbox = creditItem.querySelector('input[type="checkbox"]:checked');
        if (checkbox) {
            // Get the first input field value (all should be synced)
            const inputField = creditItem.querySelector('input[type="number"]');
            if (inputField) {
                totalCredits += parseInt(inputField.value) || 0;
            }
        }
    });

    const effectiveFee = annualFee - totalCredits;

    // Update display
    document.getElementById('total-credits').textContent = totalCredits;
    const feeElement = document.getElementById('effective-fee');

    if (effectiveFee > 0) {
        feeElement.textContent = '$' + effectiveFee;
        feeElement.className = 'effective-fee positive';
    } else if (effectiveFee === 0) {
        feeElement.textContent = '$0';
        feeElement.className = 'effective-fee';
    } else {
        feeElement.textContent = '+$' + Math.abs(effectiveFee);
        feeElement.className = 'effective-fee negative';
    }
}

// Modern Collapsible Section Functionality
function toggleCalculatorSection() {
    const header = document.querySelector('.calculator-header');
    const content = document.querySelector('.calculator-content');
    const isExpanded = header.getAttribute('aria-expanded') === 'true';
    
    header.setAttribute('aria-expanded', !isExpanded);
    
    if (isExpanded) {
        content.classList.add('collapsed');
    } else {
        content.classList.remove('collapsed');
    }
    
    localStorage.setItem('calculatorExpanded', !isExpanded);
}

function handleKeyToggle(event) {
    if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        toggleCalculatorSection();
    }
}

// Initialize section state on page load
function initializeCalculatorSection() {
    const savedState = localStorage.getItem('calculatorExpanded');
    const header = document.querySelector('.calculator-header');
    const content = document.querySelector('.calculator-content');
    
    if (savedState !== null) {
        const isExpanded = savedState === 'true';
        header.setAttribute('aria-expanded', isExpanded);
        
        if (!isExpanded) {
            content.classList.add('collapsed');
        }
    }
} 