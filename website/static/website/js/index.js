document.addEventListener('DOMContentLoaded', function() {
    const grid = document.getElementById('instructorGrid');
    const prevBtn = document.getElementById('prevBtn');
    const nextBtn = document.getElementById('nextBtn');
    const cards = document.querySelectorAll('.instructor-card');
    
    if (!grid || cards.length === 0) return;

    let currentIndex = 0;
    let visibleCards = 3; // Show exactly 3 cards at a time
    let cardWidth = 280; // Default width (matches CSS)
    const gap = 25; // Matches grid gap in CSS
    
    // Check screen width to adjust card width for mobile
    const updateCardWidth = () => {
        if (window.innerWidth <= 480) {
            cardWidth = 220;
        } else {
            cardWidth = 280;
        }
    };

    // Calculate max possible index based on total cards and visible cards
    const getMaxIndex = () => {
        const totalCards = cards.length;
        return Math.max(0, totalCards - visibleCards);
    };

    const updateSlider = () => {
        // Move by exact card width + gap
        const offset = currentIndex * (cardWidth + gap);
        grid.style.transform = `translateX(-${offset}px)`;
        
        // Update button states
        const maxIndex = getMaxIndex();
        prevBtn.disabled = currentIndex === 0;
        nextBtn.disabled = currentIndex >= maxIndex;
    };

    // Initialize
    updateCardWidth();
    updateSlider();

    // Event Listeners
    nextBtn.addEventListener('click', () => {
        const maxIndex = getMaxIndex();
        if (currentIndex < maxIndex) {
            currentIndex++;
            updateSlider();
        }
    });

    prevBtn.addEventListener('click', () => {
        if (currentIndex > 0) {
            currentIndex--;
            updateSlider();
        }
    });

    // Handle resize
    let resizeTimer;
    window.addEventListener('resize', () => {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(() => {
            updateCardWidth();
            // Reset index if it exceeds new max
            const maxIndex = getMaxIndex();
            if (currentIndex > maxIndex) {
                currentIndex = maxIndex;
            }
            updateSlider();
        }, 200);
    });
});
