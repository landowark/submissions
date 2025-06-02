var backend;
new QWebChannel(qt.webChannelTransport, function (channel) {
  backend = channel.objects.backend;
});