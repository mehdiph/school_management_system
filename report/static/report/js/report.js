/* Report Page Scripts */
document.addEventListener('DOMContentLoaded', function () {
    // Optional: Auto-print functionality if requested via query param
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.has('print')) {
        window.print();
    }
});
