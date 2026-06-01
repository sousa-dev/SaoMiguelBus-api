function styleHeader(project) {
    // Dynamically change href, src, and text content
    var backArrow = document.getElementById('backArrow');
    var logoLink = document.getElementById('logoLink');
    var logoImage = document.getElementById('logoImage');
    var logoText = document.getElementById('logoText');

    // Variables for new values
    var logoHref = '/'; // Change this to your desired URL
    var newSrc = '/media/logo.png'; // Change this to your desired image path
    var newText = project;

    // Update elements
    backArrow.addEventListener('click', function(event) {
        event.preventDefault();
        window.history.back();
    });
    logoLink.href = logoHref;
    logoImage.src = newSrc;
    logoText.textContent = newText;
}