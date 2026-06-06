
const courseCards = document.querySelectorAll('.course-card')

for (let i=0; i < courseCards.length; i++){
    courseCards[i].addEventListener('click', async () => {
        // Send GET request (ignore response)
        await fetch('/some-action?param=value', { method: 'GET' });
        // Then refresh the current page
        window.location.reload();
    });
}

