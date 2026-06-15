document.addEventListener('DOMContentLoaded', function() {
    // ===== اسکریپت اسلایدر بزرگ بالای صفحه (تصاویر تمام‌صفحه در پس‌زمینه) =====
    const slides = document.querySelectorAll('.main-slide');
    const mainPrevBtn = document.getElementById('mainSlidePrev');
    const mainNextBtn = document.getElementById('mainSlideNext');
    const mainDotsContainer = document.getElementById('mainSlideDots');
    const totalSlides = slides.length;
    let activeSlideIndex = 0;
    let autoSlideInterval;

    if (totalSlides > 0 && mainDotsContainer) {
        // ساخت خودکار نقاط موقعیت‌نما (Dots)
        for (let i = 0; i < totalSlides; i++) {
            const dot = document.createElement('div');
            dot.classList.add('slide-dot');
            if (i === 0) dot.classList.add('active');
            
            dot.addEventListener('click', () => {
                activeSlideIndex = i;
                updateMainSlider();
                resetAutoSlide();
            });
            mainDotsContainer.appendChild(dot);
        }

        const updateMainSlider = () => {
            // تغییر اسلاید فعال بر اساس کلاس active
            slides.forEach((slide, idx) => {
                if (idx === activeSlideIndex) {
                    slide.classList.add('active');
                } else {
                    slide.classList.remove('active');
                }
            });

            // به‌روزرسانی نقاط موقعیت‌نما
            const dots = mainDotsContainer.querySelectorAll('.slide-dot');
            dots.forEach((dot, idx) => {
                if (idx === activeSlideIndex) {
                    dot.classList.add('active');
                } else {
                    dot.classList.remove('active');
                }
            });
        };

        const nextSlide = () => {
            activeSlideIndex = (activeSlideIndex + 1) % totalSlides;
            updateMainSlider();
        };

        const prevSlide = () => {
            activeSlideIndex = (activeSlideIndex - 1 + totalSlides) % totalSlides;
            updateMainSlider();
        };

        mainNextBtn.addEventListener('click', () => {
            nextSlide();
            resetAutoSlide();
        });

        mainPrevBtn.addEventListener('click', () => {
            prevSlide();
            resetAutoSlide();
        });

        // حرکت خودکار اسلایدر
        const startAutoSlide = () => {
            autoSlideInterval = setInterval(nextSlide, 6000); // زمان تعویض ۶ ثانیه
        };

        const resetAutoSlide = () => {
            clearInterval(autoSlideInterval);
            startAutoSlide();
        };

        startAutoSlide();
    }

    // ===== اسکریپت اسلایدر اساتید (کدهای قبلی) =====
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