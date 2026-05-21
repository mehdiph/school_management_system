const formContainer = document.querySelector('.form-container');
const usernameInput = document.querySelector('.username-input > input');

formContainer.addEventListener('fullscreenchange', function(event){
    usernameInput.focus()
});
