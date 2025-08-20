// Shared Card Page Scripts - Update this file to change all card pages

// Load header and footer
document.addEventListener('DOMContentLoaded', function() {
    loadComponent('../../header.html', 'header-placeholder', 'header-fallback');
    loadComponent('../../footer.html', 'footer-placeholder', 'footer-fallback');
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
}); 

// Initialize calculator placeholders to show $0 when toggles are off
function initializeCalculatorPlaceholders() {
    const checkboxes = document.querySelectorAll('input[type="checkbox"]');
    
    checkboxes.forEach(checkbox => {
        const creditItem = checkbox.closest('.table-row');
        const placeholder = creditItem.querySelector('.value-placeholder');
        const valueInput = creditItem.querySelector('.value-input');
        
        if (placeholder && valueInput) {
            if (!checkbox.checked) {
                placeholder.style.display = 'block';
                placeholder.textContent = '$0';
                valueInput.classList.remove('active');
            } else {
                placeholder.style.display = 'none';
                valueInput.classList.add('active');
            }
        }
    });
}

// Toggle credit function - sets input to max value when toggled on
function toggleCredit(checkbox) {
    const creditItem = checkbox.closest('.table-row');
    const inputField = creditItem.querySelector('input[type="number"]');
    const valueInput = creditItem.querySelector('.value-input');
    const placeholder = creditItem.querySelector('.value-placeholder');
    const maxValue = parseInt(checkbox.getAttribute('data-max'));
    
    if (checkbox.checked) {
        inputField.value = maxValue;
        valueInput.classList.add('active');
        placeholder.style.display = 'none';
    } else {
        inputField.value = 0;
        valueInput.classList.remove('active');
        placeholder.style.display = 'block';
        placeholder.textContent = '$0';
    }
    
    updateCalculation();
}

// Generic calculator functionality - each page should define its own annualFee variable
function updateCalculation() {
    if (typeof annualFee === 'undefined') {
        console.warn('annualFee not defined on this page');
        return;
    }
    
    const checkboxes = document.querySelectorAll('input[type="checkbox"]:checked');
    
    let totalCredits = 0;
    checkboxes.forEach(checkbox => {
        // Find the corresponding input field for this credit item
        const creditItem = checkbox.closest('.table-row');
        const inputField = creditItem.querySelector('input[type="number"]');
        if (inputField) {
            totalCredits += parseInt(inputField.value) || 0;
        }
    });

    const effectiveFee = annualFee - totalCredits;

    // Update display
    document.getElementById('total-credits').textContent = totalCredits;
    const feeElement = document.getElementById('effective-fee');
    const interpretationElement = document.getElementById('fee-interpretation');

    if (effectiveFee > 0) {
        feeElement.textContent = '$' + effectiveFee;
        feeElement.className = 'effective-fee positive';
        interpretationElement.textContent = 'You still pay $' + effectiveFee + ' annually after credits';
    } else if (effectiveFee === 0) {
        feeElement.textContent = '$0';
        feeElement.className = 'effective-fee';
        interpretationElement.textContent = 'The credits exactly cover the annual fee!';
    } else {
        feeElement.textContent = '+$' + Math.abs(effectiveFee);
        feeElement.className = 'effective-fee negative';
        interpretationElement.textContent = 'You come out ahead by $' + Math.abs(effectiveFee) + ' per year!';
    }
} 