// Shared Card Page Scripts - Update this file to change all card pages

// Load header and footer
document.addEventListener('DOMContentLoaded', function() {
    const headerPath = getRootPath('header.html');
    const footerPath = getRootPath('footer.html');
    loadComponent(headerPath, 'header-placeholder', 'header-fallback');
    loadComponent(footerPath, 'footer-placeholder', 'footer-fallback');
    
    // Initialize calculator placeholders when page loads
    initializeCalculatorPlaceholders();
});

// Build an absolute path from site root so it works from any subdirectory
function getRootPath(fileName) {
    return window.location.origin + '/' + fileName;
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
                        console.log(`Executing header script ${index + 1}`);
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
            console.log('Loading fallback content instead');
            placeholder.innerHTML = getFallbackContent(filename);
            // Also try to initialize for fallback content
            if (filename.includes('header.html')) {
                initializeLoadedContent();
            }
        });
}

function getFallbackContent(filename) {
    if (filename.includes('header.html')) {
        return `
            <style>
                .mobile-menu-toggle { display: none; width: 44px; height: 44px; background: transparent; border: none; cursor: pointer; border-radius: 8px; position: relative; }
                .hamburger { width: 20px; height: 20px; position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); }
                .hamburger span { width: 20px; height: 3px; background: #059669; border-radius: 2px; position: absolute; left: 0; transition: all 0.3s ease; }
                .hamburger span:nth-child(1) { top: 1px; }
                .hamburger span:nth-child(2) { top: 6px; }
                .hamburger span:nth-child(3) { top: 11px; }
                .mobile-menu { position: fixed; top: 70px; right: -320px; width: 320px; height: calc(100vh - 70px); background: linear-gradient(135deg, #fafaf9 0%, #f5f5f4 100%); z-index: 99999; box-shadow: -4px 0 20px rgba(5, 150, 105, 0.15); transition: right 0.4s cubic-bezier(0.25, 0.46, 0.45, 0.94); overflow-y: auto; border-left: 2px solid #10b981; }
                .mobile-menu.active { right: 0; }
                .mobile-menu-overlay { position: fixed; top: 70px; left: 0; width: 100%; height: calc(100vh - 70px); background: rgba(4, 120, 87, 0.15); backdrop-filter: blur(4px); z-index: 99998; opacity: 0; visibility: hidden; transition: opacity 0.4s cubic-bezier(0.25, 0.46, 0.45, 0.94), visibility 0.4s cubic-bezier(0.25, 0.46, 0.45, 0.94); }
                .mobile-menu-overlay.active { opacity: 1; visibility: visible; }
                .mobile-nav-links { list-style: none; padding: 1rem 0 1rem 0; margin: 0; }
                .mobile-nav-links li { margin: 0.5rem 1rem; border-radius: 12px; overflow: hidden; transition: all 0.3s ease; }
                .mobile-nav-links a { display: block; padding: 1rem 1.5rem; color: #57534e; text-decoration: none; font-weight: 600; font-size: 1.1rem; transition: all 0.3s ease; position: relative; border-radius: 12px; }
                @media (max-width: 768px) { .mobile-menu-toggle { display: flex; } .nav-links { display: none; } nav { padding: 0 1rem; height: 70px; } }
            </style>
            <header style="background: rgba(250, 250, 249, 0.95); backdrop-filter: blur(12px); box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.1), 0 1px 2px 0 rgba(0, 0, 0, 0.06); position: sticky; top: 0; z-index: 1000; width: 100%; border-bottom: 1px solid #e7e5e4;">
                <nav style="max-width: 1400px; margin: 0 auto; padding: 0 2rem; display: flex; justify-content: space-between; align-items: center; height: 80px;">
                    <a href="#" class="logo" style="font-size: 1.5rem; font-weight: 700; color: #059669; text-decoration: none;">Practical Rewards</a>
                    
                    <button class="mobile-menu-toggle" id="mobile-menu-toggle">
                        <div class="hamburger">
                            <span></span>
                            <span></span>
                            <span></span>
                        </div>
                    </button>
                    
                    <ul class="nav-links" style="display: flex; list-style: none; gap: 2rem; margin: 0; padding: 0;">
                        <li><a href="#" style="color: #57534e; text-decoration: none; font-weight: 500;">Home</a></li>
                        <li><a href="#" style="color: #57534e; text-decoration: none; font-weight: 500;">Learning</a></li>
                        <li><a href="#" style="color: #57534e; text-decoration: none; font-weight: 500;">Calculator</a></li>
                        <li><a href="#" style="color: #57534e; text-decoration: none; font-weight: 500;">About</a></li>
                    </ul>
                </nav>
            </header>
            
            <div class="mobile-menu-overlay" id="mobile-menu-overlay"></div>
            <div class="mobile-menu" id="mobile-menu">
                <ul class="mobile-nav-links">
                    <li><a href="/index.html">Home</a></li>
                    <li><a href="/learning.html">Learning</a></li>
                    <li><a href="/cards.html">Cards</a></li>
                    <li><a href="/about.html">About</a></li>
                    <li><a href="/contact.html">Contact</a></li>
                </ul>
            </div>
            <script>
            // Setup mobile menu for fallback header
            function setupFallbackMobileMenu() {
                const toggle = document.getElementById('mobile-menu-toggle');
                const menu = document.getElementById('mobile-menu');
                const overlay = document.getElementById('mobile-menu-overlay');
                
                if (!toggle || !menu || !overlay) return;
                
                function openMenu() {
                    overlay.classList.add('active');
                    menu.classList.add('active');
                    document.body.style.overflow = 'hidden';
                }
                
                function closeMenu() {
                    overlay.classList.remove('active');
                    menu.classList.remove('active');
                    document.body.style.overflow = '';
                }
                
                toggle.onclick = function(e) {
                    e.preventDefault();
                    e.stopPropagation();
                    if (menu.classList.contains('active')) {
                        closeMenu();
                    } else {
                        openMenu();
                    }
                };
                
                overlay.onclick = function(e) {
                    if (e.target === overlay) {
                        closeMenu();
                    }
                };
                
                document.onkeydown = function(e) {
                    if (e.key === 'Escape') {
                        closeMenu();
                    }
                };
            }
            
            // Setup mobile menu immediately for fallback
            setupFallbackMobileMenu();
            window.setupMobileMenu = setupFallbackMobileMenu;
            
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