const container = document.querySelector('.subject-sessions')
const template = document.getElementById('subject-sessions-template');
const coursesGridSection = document.querySelector('.courses-grid');

coursesGridSection.addEventListener('click', function (event){
    const courseCard = event.target.closest('.course-card');
    const courseSlug = courseCard.dataset.subjectSlug

    function renderSessions(container, sessions){
        container.innerHTML = '';

        sessions.forEach(session => {
            const clone = template.content.cloneNode(true);
            clone.getElementById('session-badge-date').textContent = session.label;
            clone.getElementById('session-main-title').textContent = session.title;
            clone.getElementById('session-main-desc').textContent = session.content;

            container.appendChild(clone);
        });
    }

    fetch(`/student/api/sessions/${courseSlug}`)
        .then(response => {
            if (!response.ok) throw new Error('Network error');
                return response.json();
        })
        .then(data => renderSessions(container, data.sessions))
})

