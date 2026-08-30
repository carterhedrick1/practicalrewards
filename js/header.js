// Shared chrome loader and mobile menu functionality
// Root-absolute component paths work from both root pages and subdirectories.
document.addEventListener('DOMContentLoaded', function() {
    loadSharedComponent('/header.html', 'header-placeholder', function() {
        initializeMobileMenu();
    });
    loadSharedComponent('/footer.html', 'footer-placeholder');
});

function loadSharedComponent(componentPath, placeholderId, onLoad) {
    const placeholder = document.getElementById(placeholderId);

    if (!placeholder) {
        return;
    }

    fetch(componentPath)
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            return response.text();
        })
        .then(data => {
            // Component scripts are not executed by innerHTML. The loader handles
            // header initialization below, and shared links are root-absolute.
            placeholder.innerHTML = data;

            if (typeof onLoad === 'function') {
                onLoad();
            }
        })
        .catch(error => {
            console.error(`Error loading ${componentPath}:`, error);
        });
}

function initializeMobileMenu() {
    const toggle = document.getElementById('mobile-menu-toggle');
    const menu = document.getElementById('mobile-menu');
    const overlay = document.getElementById('mobile-menu-overlay');
    const close = document.getElementById('mobile-menu-close');

    if (!toggle || !menu || !overlay) {
        console.log('Mobile menu elements not found');
        return;
    }

    // Ensure overlay is hidden initially
    overlay.style.display = 'none';

    function openMenu() {
        menu.classList.add('active');
        overlay.classList.add('active');
        overlay.style.display = 'block';
        toggle.classList.add('active');
        document.body.style.overflow = 'hidden';
        
        // Force overlay to be on top but below menu
        overlay.style.zIndex = '998';
        menu.style.zIndex = '1000';
    }

    function closeMenu() {
        menu.classList.remove('active');
        overlay.classList.remove('active');
        toggle.classList.remove('active');
        document.body.style.overflow = '';
        
        // Hide overlay completely when closed
        setTimeout(() => {
            if (!overlay.classList.contains('active')) {
                overlay.style.display = 'none';
            }
        }, 300);
    }

    // Click hamburger to toggle
    toggle.addEventListener('click', function(e) {
        e.preventDefault();
        e.stopPropagation();
        
        if (menu.classList.contains('active')) {
            closeMenu();
        } else {
            openMenu();
        }
    });

    // Touch support for mobile - separate handler
    toggle.addEventListener('touchend', function(e) {
        e.preventDefault();
        e.stopPropagation();
        
        if (menu.classList.contains('active')) {
            closeMenu();
        } else {
            openMenu();
        }
    });

    // Click overlay to close
    overlay.addEventListener('click', function(e) {
        e.preventDefault();
        e.stopPropagation();
        closeMenu();
    });

    // Close button
    if (close) {
        close.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            closeMenu();
        });
    }

    // Close when clicking nav links
    const mobileNavLinks = document.querySelectorAll('.mobile-nav-links a');
    mobileNavLinks.forEach(link => {
        link.addEventListener('click', function() {
            closeMenu();
        });
    });

    // Close menu when clicking outside (additional safety)
    document.addEventListener('click', function(e) {
        if (menu.classList.contains('active') && 
            !menu.contains(e.target) && 
            !toggle.contains(e.target)) {
            closeMenu();
        }
    });

    console.log('Mobile menu initialized successfully');
}
