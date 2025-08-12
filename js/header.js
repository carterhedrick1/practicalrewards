// Header loader and mobile menu functionality - Enhanced for complex pages
document.addEventListener('DOMContentLoaded', function() {
    // Wait a bit for other page scripts to initialize first
    setTimeout(function() {
        fetch('header.html')
            .then(response => response.text())
            .then(data => {
                document.getElementById('header-placeholder').innerHTML = data;
                
                // Initialize mobile menu after header loads
                setTimeout(function() {
                    const toggle = document.getElementById('mobile-menu-toggle');
                    const menu = document.getElementById('mobile-menu');
                    const overlay = document.getElementById('mobile-menu-overlay');
                    const close = document.getElementById('mobile-menu-close');

                    if (!toggle || !menu || !overlay) {
                        console.log('Mobile menu elements not found');
                        return;
                    }

                    function openMenu() {
                        menu.classList.add('active');
                        overlay.classList.add('active');
                        toggle.classList.add('active');
                        document.body.style.overflow = 'hidden';
                    }

                    function closeMenu() {
                        menu.classList.remove('active');
                        overlay.classList.remove('active');
                        toggle.classList.remove('active');
                        document.body.style.overflow = '';
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

                    // Touch support for mobile
                    toggle.addEventListener('touchstart', function(e) {
                        e.preventDefault();
                        e.stopPropagation();
                        if (menu.classList.contains('active')) {
                            closeMenu();
                        } else {
                            openMenu();
                        }
                    });

                    // Click overlay or close button to close
                    overlay.addEventListener('click', closeMenu);
                    if (close) close.addEventListener('click', closeMenu);

                    // Close when clicking nav links
                    document.querySelectorAll('.mobile-nav-links a').forEach(link => {
                        link.addEventListener('click', closeMenu);
                    });

                    console.log('Mobile menu initialized successfully');
                }, 600);
            })
            .catch(error => {
                console.error('Error loading header:', error);
            });
    }, 200);
});