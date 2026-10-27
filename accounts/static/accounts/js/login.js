const formContainer = document.querySelector('.form-container');
const usernameInput = document.querySelector('.username-input > input');

// The login page may not have these elements; skip instead of throwing.
if (formContainer && usernameInput) {
    formContainer.addEventListener('fullscreenchange', function(event){
        usernameInput.focus()
    });
}
