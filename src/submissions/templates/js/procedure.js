document.addEventListener('DOMContentLoaded', function() {
    var links = document.querySelectorAll('a.data-link');

    links.forEach(function(link) {
        link.addEventListener('click', function() {
            var classArray = Array.from(this.classList).filter(function(cls) {
                return cls !== 'data-link';
            });
            console.log('Clicked element id:', this.id);
            console.log('Other classes:', classArray);

            if (window.backend && typeof window.backend.show_sub_details === 'function') {
                window.backend.show_sub_details(this.id, classArray.join(' '));
            } else {
                console.error('Backend function show_sub_details is not available.');
            }
        });
    });

    
});
