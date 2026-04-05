// scripts/load-toc.js
async function injectTOC() {
    const placeholder = document.getElementById('toc-placeholder');
    if (placeholder) {
        try {
            // Adjust the path to where your contents.html is located
            const response = await fetch('/component/contents.html');
            const html = await response.text();
            placeholder.innerHTML = html;
        } catch (err) {
            console.error("Failed to load Table of Contents:", err);
        }
    }
}

// Run the function when the page loads
window.addEventListener('DOMContentLoaded', injectTOC);
