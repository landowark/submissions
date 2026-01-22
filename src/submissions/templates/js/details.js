

var backend;
if (typeof QWebChannel !== 'undefined') {
    new QWebChannel(qt.webChannelTransport, function(channel) {
        backend = channel.objects.backend;
        console.log('QWebChannel ready, backend:', backend);
    });
} else {
    console.warn('QWebChannel or qt not available yet - make sure qwebchannel.js is included');
}