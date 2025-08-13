// Header loader and mobile menu functionality - Fixed version
document.addEventListener('DOMContentLoaded', function() {
    // Wait a bit for other page scripts to initialize first
    setTimeout(function() {
        fetch('header.html')
            .then(response => response.text())
            .then(data => {
                document.getElementById('header-placeholder').innerHTML = data;
                
                // Initialize mobile menu after header loads
                setTimeout(function() {
                    initializeMobileMenu();
                }, 100);
            })
            .catch(error => {
                console.error('Error loading header:', error);
            });
    }, 100);
});

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