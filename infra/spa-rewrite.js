// CloudFront Function (viewer-request) for the S3 single-page app origin.
// Requests for client-side routes such as /projects/123 have no file extension
// and no matching S3 object; serve index.html so React Router can handle them.
function handler(event) {
  var request = event.request;
  var uri = request.uri;
  var lastSegment = uri.substring(uri.lastIndexOf('/') + 1);
  if (lastSegment.indexOf('.') === -1) {
    request.uri = '/index.html';
  }
  return request;
}
