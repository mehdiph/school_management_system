function toggleView(viewType) {
    // Update buttons
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    // active class is set on button click target, this assumes event is available in scope or passed. 
    // Best practice is to pass 'this' or use event listener, but adhering to the original inline onclick style for simplicity of refactor.
    // The original code used `event.target`.
    if (event && event.target) {
        event.target.classList.add('active');
    }

    // Toggle Content
    const subjectView = document.getElementById('view-by-subject');
    const gradeView = document.getElementById('view-by-grade');

    if (viewType === 'by-subject') {
        if (subjectView) subjectView.style.display = 'block';
        if (gradeView) gradeView.style.display = 'none';
    } else {
        if (subjectView) subjectView.style.display = 'none';
        if (gradeView) gradeView.style.display = 'block';
    }
}
