function styleOAuthLinks() {
    // Select the OAuth links in the third-party section
    const oauthLinks = document.querySelectorAll('ul li a');

    oauthLinks.forEach(link => {
        const provider = link.title.trim(); // Get the provider from the title attribute
        let iconClass = '';

        if (provider.toLowerCase() === 'google') {
            iconClass = 'fab fa-google'; // Font Awesome class for Google
        } else if (provider.toLowerCase() === 'github') {
            iconClass = 'fab fa-github'; // Font Awesome class for GitHub
        }

        if (iconClass) {
            const icon = document.createElement('i');
            icon.className = iconClass;

            // Add the class to apply button styles
            link.classList.add('oauth-button');
            link.textContent = `Sign in with ${provider}`; // Update text
            link.prepend(icon); // Add the icon before the link text
        }
    });
}