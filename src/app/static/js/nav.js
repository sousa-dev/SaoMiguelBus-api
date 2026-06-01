document.addEventListener('DOMContentLoaded', function() {
    const hamburger = document.querySelector('.hamburger');
    const navLinks = document.querySelector('.nav-links');
    const navBar = document.querySelector('nav');
    const dropdownToggle = document.querySelector('.dropdown-toggle');
    const dropdownContent = document.querySelector('.dropdown-content');

    // Toggle mobile menu
    function toggleMenu() {
        if (navLinks.classList.contains('hidden')) {
            navLinks.classList.remove('hidden');
            navLinks.classList.add('flex');
            hamburger.innerHTML = '&times;';
            navBar.classList.add('menu-active');
        } else {
            navLinks.classList.add('hidden');
            navLinks.classList.remove('flex');
            hamburger.innerHTML = '&#9776;';
            navBar.classList.remove('menu-active');
        }
    }

    hamburger.addEventListener('click', toggleMenu);

    window.addEventListener('resize', () => {
        if (window.innerWidth > 1024) { // Change to lg breakpoint
            navLinks.classList.add('hidden');
            navLinks.classList.remove('flex');
            hamburger.innerHTML = '&#9776;';
            navBar.classList.remove('menu-active');
        }
    });

    // Toggle dropdown on click
    dropdownToggle.addEventListener('click', function(event) {
        event.preventDefault();
        event.stopPropagation();
        if (!dropdownContent.classList.contains('hidden')) {
            dropdownContent.classList.add('hidden');
        }
    });

    // Hide dropdown when clicking outside
    document.addEventListener('click', function(event) {
        if (!dropdownContent.classList.contains('hidden')) {
            dropdownContent.classList.add('hidden');
        }
    });

    // Prevent dropdown from closing when clicking inside
    dropdownContent.addEventListener('click', function(event) {
        event.stopPropagation();
    });
});