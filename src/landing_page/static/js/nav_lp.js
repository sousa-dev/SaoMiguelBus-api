document.addEventListener('DOMContentLoaded', function() {
    const hamburger = document.querySelector('.hamburger');
    const navLinks = document.querySelector('.nav-links');
    const navBar = document.querySelector('nav'); 

    function toggleMenu() {
        if (navLinks.style.display === 'flex') {
            navLinks.style.display = 'none';
            hamburger.innerHTML = '&#9776;';
            navBar.classList.remove('menu-active'); 
        } else {
            navLinks.style.display = 'flex';
            hamburger.innerHTML = '&times;';
            navBar.classList.add('menu-active');
        }
    }

    hamburger.addEventListener('click', toggleMenu);

    window.addEventListener('resize', () => {
        if (window.innerWidth > 768) {
            navLinks.style.display = '';
            hamburger.innerHTML = '&#9776;';
            navBar.classList.remove('menu-active'); 
        }
    });

    const dropdowns = document.querySelectorAll('.nav-links .dropdown');
    dropdowns.forEach(dropdown => {
        const dropdownToggle = dropdown.querySelector('a');
        const dropdownContent = dropdown.querySelector('.dropdown-content');

        dropdownToggle.addEventListener('click', function(event) {
            event.preventDefault();
            event.stopPropagation();

            const isActive = dropdown.classList.contains('active');

            dropdowns.forEach(d => {
                d.classList.remove('active');
                d.querySelector('.dropdown-content').style.display = 'none';
            });

            if (!isActive) {
                dropdown.classList.add('active');
                dropdownContent.style.display = 'block';
            }
        });
    });

    document.addEventListener('click', function(event) {
        dropdowns.forEach(dropdown => {
            let dropdownContent = dropdown.querySelector('.dropdown-content');
            if (dropdownContent.style.display === 'block') {
                dropdownContent.style.display = 'none';
                dropdown.classList.remove('active');
            }
        });
    });
});