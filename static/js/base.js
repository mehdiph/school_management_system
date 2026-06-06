// const messages = document.querySelector('.messages')


// setTimeout(function (element, duration=300){
//     const keyframes = [
//     { height: `${element.offsetHeight}px`, opacity: 1, margin: 'inherit', padding: 'inherit' },
//     { height: '0px', opacity: 0, margin: '0', padding: '0' }
//   ];
//   const options = { duration, easing: 'ease-out', fill: 'forwards' };
//   const animation = element.animate(keyframes, options);
  
//   animation.onfinish = () => element.remove();
// }, 5000, messages, 900)


(function() {
    // Configure auto-dismiss timeout (milliseconds)
    const AUTO_DISMISS_DELAY = 5000000;  // 5 seconds

    // Function to add close button and attach dismiss logic to a single message
    function enhanceMessage(messageEl) {
      // Avoid double enhancement
      if (messageEl.dataset.enhanced === 'true') return;
      messageEl.dataset.enhanced = 'true';

      // Create close button
      const closeBtn = document.createElement('button');
      closeBtn.className = 'msg-close';
      closeBtn.innerHTML = '✕';
      closeBtn.setAttribute('aria-label', 'Dismiss message');
      messageEl.appendChild(closeBtn);

      // Function to trigger exit animation and remove element
      const dismissMessage = () => {
        // If already exiting, ignore
        if (messageEl.classList.contains('alert-exit')) return;
        messageEl.classList.add('alert-exit');
        // Remove from DOM after animation ends
        messageEl.addEventListener('animationend', () => {
          if (messageEl.parentNode) messageEl.remove();
        }, { once: true });
        // Fallback in case animationend doesn't fire
        setTimeout(() => {
          if (messageEl.parentNode) messageEl.remove();
        }, 350);
      };

      // Auto-dismiss after delay
      let timeoutId = setTimeout(dismissMessage, AUTO_DISMISS_DELAY);

      // Click on close button dismisses immediately
      closeBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        clearTimeout(timeoutId);
        dismissMessage();
      });

      // Optional: clicking on the message itself also dismisses (comment out if you don't want)
      // messageEl.addEventListener('click', (e) => {
      //   if (e.target !== closeBtn) {
      //     clearTimeout(timeoutId);
      //     dismissMessage();
      //   }
      // });
    }

    // Enhance all existing messages
    function enhanceAllMessages() {
      document.querySelectorAll('.messages .alert').forEach(enhanceMessage);
    }

    // Watch for dynamically added messages (e.g., HTMX, AJAX)
    function observeNewMessages() {
      const messagesContainer = document.querySelector('.messages');
      if (!messagesContainer) return;

      const observer = new MutationObserver((mutations) => {
        mutations.forEach((mutation) => {
          mutation.addedNodes.forEach((node) => {
            if (node.nodeType === 1 && node.matches && node.matches('.alert')) {
              enhanceMessage(node);
            } else if (node.nodeType === 1 && node.querySelector) {
              node.querySelectorAll('.alert').forEach(enhanceMessage);
            }
          });
        });
      });

      observer.observe(messagesContainer, { childList: true, subtree: true });
    }

    // Initialise when DOM is ready
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', () => {
        enhanceAllMessages();
        observeNewMessages();
      });
    } else {
      enhanceAllMessages();
      observeNewMessages();
    }
  })();