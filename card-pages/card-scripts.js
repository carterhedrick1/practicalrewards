// Shared Card Page Scripts - Update this file to change all card pages

// Immediate initialization to fix arrow state
if (document.readyState === 'loading') {
    // DOM is still loading, wait for it
    document.addEventListener('DOMContentLoaded', function() {
        setTimeout(initializeCalculatorSection, 0);
    });
} else {
    // DOM is already loaded, run immediately
    setTimeout(initializeCalculatorSection, 0);
}

// Load header and footer
document.addEventListener('DOMContentLoaded', function() {
    const headerPath = getRootPath('header.html');
    const footerPath = getRootPath('footer.html');
    loadComponent(headerPath, 'header-placeholder', 'header-fallback');
    loadComponent(footerPath, 'footer-placeholder', 'footer-fallback');
    
    // Initialize calculator placeholders when page loads
    initializeCalculatorPlaceholders();
    
    // Initialize calculator section state
    initializeCalculatorSection();
});

// Build a relative path that works from the card-pages subdirectory
function getRootPath(fileName) {
    return '../' + fileName;
}

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
            console.log(`Successfully loaded ${filename}`);

            // If loading the header, execute its inline scripts (to register setupMobileMenu),
            // then insert the script-free HTML like the index page does
            if (filename.includes('header.html')) {
                // Extract inline scripts
                const scriptRegex = /<script[^>]*>([\s\S]*?)<\/script>/gi;
                const scripts = [];
                let match;

                while ((match = scriptRegex.exec(html)) !== null) {
                    scripts.push(match[1]);
                }

                // Execute scripts safely
                scripts.forEach((script, index) => {
                    try {
                        eval(script);
                    } catch (error) {
                        console.error(`Error executing header script ${index + 1}:`, error);
                    }
                });

                // Remove scripts from HTML before inserting
                const cleanHtml = html.replace(/<script[^>]*>[\s\S]*?<\/script>/gi, '');
                placeholder.innerHTML = cleanHtml;
            } else {
                // Non-header content: insert as-is
                placeholder.innerHTML = html;
            }

            // Initialize after DOM insertion
            initializeLoadedContent();
        })
        .catch(error => {
            console.warn(`Could not load ${filename}:`, error);
            // Do not render a fallback header on card pages; only fallback non-header components
            if (!filename.includes('header.html')) {
                console.log('Loading fallback content instead');
                placeholder.innerHTML = getFallbackContent(filename);
                initializeLoadedContent();
            }
        });
}

function getFallbackContent(filename) {
    if (filename.includes('header.html')) {
        // No fallback header for card pages
        return '';
    } else if (filename.includes('footer.html')) {
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
    if (typeof window.attachHeaderScrollBehavior === 'function') {
        window.attachHeaderScrollBehavior();
    }
    
    // Initialize mobile menu after header loads
    setTimeout(() => {
        console.log('initializeLoadedContent: Setting up mobile menu...');
        if (typeof window.setupMobileMenu === 'function') {
            console.log('initializeLoadedContent: Calling setupMobileMenu...');
            window.setupMobileMenu();
        } else {
            console.log('initializeLoadedContent: setupMobileMenu function not found, using local setup...');
            setupLocalMobileMenu();
        }

        // Fix navigation paths for subdirectory compatibility
        if (typeof window.fixNavigationPaths === 'function') {
            console.log('initializeLoadedContent: Fixing navigation paths...');
            window.fixNavigationPaths();
        }
        
        if (typeof window.fixFooterPaths === 'function') {
            console.log('initializeLoadedContent: Fixing footer paths...');
            window.fixFooterPaths();
        }

        // As a final safety, bind basic handlers if nothing attached yet
        bindBasicMobileMenuHandlers();
    }, 200);
}

// Local mobile menu setup function (fallback when header.html doesn't load)
function setupLocalMobileMenu() {
    console.log('setupLocalMobileMenu called, checking for elements...');
    
    const toggle = document.getElementById('mobile-menu-toggle');
    const menu = document.getElementById('mobile-menu');
    const overlay = document.getElementById('mobile-menu-overlay');
    
    console.log('Found elements:', {
        toggle: toggle ? 'YES' : 'NO',
        menu: menu ? 'YES' : 'NO',
        overlay: overlay ? 'YES' : 'NO'
    });
    
    if (!toggle || !menu || !overlay) {
        console.log('Missing mobile menu elements, cannot setup');
        return false;
    }
    
    function openMenu() {
        console.log('OPENING MENU');
        overlay.classList.add('active');
        menu.classList.add('active');
        document.body.style.overflow = 'hidden';
    }
    
    function closeMenu() {
        console.log('CLOSING MENU');
        overlay.classList.remove('active');
        menu.classList.remove('active');
        document.body.style.overflow = '';
    }
    
    // Add click handlers
    toggle.onclick = function(e) {
        e.preventDefault();
        e.stopPropagation();
        console.log('HAMBURGER CLICKED!');
        if (menu.classList.contains('active')) {
            closeMenu();
        } else {
            openMenu();
        }
    };
    
    // Close on overlay click
    overlay.onclick = function(e) {
        if (e.target === overlay) {
            console.log('Overlay clicked - closing menu');
            closeMenu();
        }
    };
    
    // Close on escape
    document.onkeydown = function(e) {
        if (e.key === 'Escape') {
            closeMenu();
        }
    };
    
    console.log('Local mobile menu setup complete!');
    return true;
}

// Idempotent basic handlers in case header script didn't bind
function bindBasicMobileMenuHandlers() {
    const toggle = document.getElementById('mobile-menu-toggle');
    const menu = document.getElementById('mobile-menu');
    const overlay = document.getElementById('mobile-menu-overlay');

    if (!toggle || !menu || !overlay) return;

    // Avoid double-binding: skip if header assigned onclick or we've bound already
    if (toggle.onclick || toggle.dataset.bound === 'true') return;

    function openMenu() {
        overlay.classList.add('active');
        menu.classList.add('active');
        overlay.style.display = 'block';
        document.body.style.overflow = 'hidden';
    }

    function closeMenu() {
        menu.classList.remove('active');
        overlay.classList.remove('active');
        document.body.style.overflow = '';
        setTimeout(() => {
            if (!overlay.classList.contains('active')) {
                overlay.style.display = 'none';
            }
        }, 300);
    }

    toggle.addEventListener('click', function(e) {
        e.preventDefault();
        e.stopPropagation();
        if (menu.classList.contains('active')) {
            closeMenu();
        } else {
            openMenu();
        }
    }, { passive: false });

    toggle.addEventListener('touchend', function(e) {
        e.preventDefault();
        e.stopPropagation();
        if (menu.classList.contains('active')) {
            closeMenu();
        } else {
            openMenu();
        }
    }, { passive: false });

    overlay.addEventListener('click', function(e) {
        if (e.target === overlay) closeMenu();
    });

    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') closeMenu();
    });

    // Mark as bound
    toggle.dataset.bound = 'true';
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
        // Update explanation for positive fee
        const explanationElement = document.querySelector('.result-explanation p');
        if (explanationElement) {
            explanationElement.textContent = 'This is effectively what you are paying for this card. It is now up to you if the perks, protections, and earning rates are worth this fee to you over other cards.';
        }
    } else if (effectiveFee === 0) {
        feeElement.textContent = '$0';
        feeElement.className = 'effective-fee';
        // Update explanation for zero fee
        const explanationElement = document.querySelector('.result-explanation p');
        if (explanationElement) {
            explanationElement.textContent = 'Your credits fully offset the annual fee. Any perks, protections, or earning rates you use are essentially free value on top.';
        }
    } else {
        feeElement.textContent = '+$' + Math.abs(effectiveFee);
        feeElement.className = 'effective-fee negative';
        // Update explanation for negative fee (credits exceed annual fee)
        const explanationElement = document.querySelector('.result-explanation p');
        if (explanationElement) {
            explanationElement.textContent = 'Your credits exceed the annual fee! You\'re getting paid to have this card. Any perks, protections, or earning rates are pure bonus value.';
        }
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
    const header = document.querySelector('.calculator-header');
    const content = document.querySelector('.calculator-content');
    
    // Always start collapsed on page refresh
    header.setAttribute('aria-expanded', 'false');
    content.classList.add('collapsed');
    
    // Clear any saved state to ensure fresh start
    localStorage.removeItem('calculatorExpanded');
    
    // Force a reflow to ensure CSS is applied
    header.offsetHeight;
} 