

// var backend;
// if (typeof QWebChannel !== 'undefined') {
//     new QWebChannel(qt.webChannelTransport, function(channel) {
//         backend = channel.objects.backend;
//         window.backend = backend;
//         console.log('QWebChannel ready, backend:', backend);
//     });
// } else {
//     console.warn('QWebChannel or qt not available yet - make sure qwebchannel.js is included');
// }

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

 // NOTE: Rich tooltips. Browsers show title="" text literally (Qt WebEngine rendered it as rich text), so any
// title containing HTML is moved to data-tooltip and shown in a floating box instead.
(function () {
    var box = null;
    var hasHtml = /<[a-z][\s\S]*>/i;

    function tooltipElement(target) {
        var el = target && target.closest ? target.closest('[title], [data-tooltip]') : null;
        if (el && el.hasAttribute('title') && hasHtml.test(el.getAttribute('title'))) {
            el.setAttribute('data-tooltip', el.getAttribute('title'));
            el.removeAttribute('title');
        }
        return el && el.hasAttribute('data-tooltip') ? el : null;
    }

    function place(x, y) {
        var r = box.getBoundingClientRect();
        box.style.left = Math.max(4, Math.min(x + 14, window.innerWidth - r.width - 4)) + 'px';
        box.style.top = Math.max(4, Math.min(y + 14, window.innerHeight - r.height - 4)) + 'px';
    }

    document.addEventListener('mouseover', function (e) {
        var el = tooltipElement(e.target);
        if (!el) { if (box) box.style.display = 'none'; return; }
        if (!box) {
            box = document.createElement('div');
            box.className = 'rich-tooltip';
            document.body.appendChild(box);
        }
        box.innerHTML = el.getAttribute('data-tooltip');
        box.style.display = 'block';
        place(e.clientX, e.clientY);
    });
    document.addEventListener('mousemove', function (e) {
        if (box && box.style.display === 'block') place(e.clientX, e.clientY);
    });
    document.documentElement.addEventListener('mouseleave', function () {
        if (box) box.style.display = 'none';
    });
})();