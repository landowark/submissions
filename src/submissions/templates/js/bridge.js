// NOTE: Connects template scripts to Python as `backend`.
// Qt: QWebChannel object. pywebview: forwards backend.<name>(...) to pywebview.api.<name>(...);
// a trailing function argument is treated as a QWebChannel-style callback and gets the result.
var backend;
if (typeof QWebChannel !== 'undefined' && typeof qt !== 'undefined') {
    new QWebChannel(qt.webChannelTransport, function(channel) {
        backend = channel.objects.backend;
        window.backend = backend;
        console.log('QWebChannel ready, backend:', backend);
    });
} else {
    backend = window.backend = new Proxy({}, {
        get: function(_, name) {
            return function() {
                var args = Array.prototype.slice.call(arguments);
                var callback = typeof args[args.length - 1] === 'function' ? args.pop() : null;
                var api = window.pywebview && window.pywebview.api;
                if (!api || typeof api[name] !== 'function') {
                    console.warn('backend.' + name + ' is not available in the web UI.');
                    return Promise.resolve(null);
                }
                var result = api[name].apply(api, args);
                if (callback) result.then(callback);
                return result;
            };
        }
    });
}