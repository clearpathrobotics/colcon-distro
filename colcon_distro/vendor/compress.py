# From: https://raw.githubusercontent.com/michaelchisari/sanic_brogz
'''
Copyright (c) 2015 by Armin Ronacher and contributors.  See AUTHORS
for more details.

Some rights reserved.

Redistribution and use in source and binary forms of the software as well
as documentation, with or without modification, are permitted provided
that the following conditions are met:

* Redistributions of source code must retain the above copyright
  notice, this list of conditions and the following disclaimer.

* Redistributions in binary form must reproduce the above
  copyright notice, this list of conditions and the following
  disclaimer in the documentation and/or other materials provided
  with the distribution.

* The names of the contributors may not be used to endorse or
  promote products derived from this software without specific
  prior written permission.

THIS SOFTWARE AND DOCUMENTATION IS PROVIDED BY THE COPYRIGHT HOLDERS AND
CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT
NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER
OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR
PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
SOFTWARE AND DOCUMENTATION, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH
DAMAGE.
'''

import gzip

DEFAULT_MIME_TYPES = frozenset([
    'text/html', 'text/css', 'text/xml',
    'application/json',
    'application/javascript'])


class Compress(object):
    def __init__(self, app=None):
        self.app = app
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        defaults = [
            ('COMPRESS_MIMETYPES', DEFAULT_MIME_TYPES),
            ('COMPRESS_LEVEL', 6),
            ('COMPRESS_MIN_SIZE', 500),
        ]

        for k, v in defaults:
            app.config.setdefault(k, v)

        @app.middleware('response')
        async def compress_response(request, response):
            return (await self._compress_response(request, response))

    async def _compress_response(self, request, response):
        accept_encoding = request.headers.get('Accept-Encoding', '')

        accepted = [w.strip() for w in accept_encoding.split(',')]

        content_length = len(response.body)
        content_type = response.content_type

        if ';' in response.content_type:
            content_type = content_type.split(';')[0]

        if (content_type not in self.app.config['COMPRESS_MIMETYPES'] or
            'gzip' not in accepted or
            not 200 <= response.status < 300 or
            (content_length is not None and
             content_length < self.app.config['COMPRESS_MIN_SIZE']) or
                'Content-Encoding' in response.headers):
            return response

        elif 'gzip' in accepted:
            compressed_content = self.gz(response)
            response.headers['Content-Encoding'] = 'gzip'

        response.body = compressed_content

        response.headers['Content-Length'] = len(response.body)

        vary = response.headers.get('Vary')
        if vary:
            if 'accept-encoding' not in vary.lower():
                response.headers['Vary'] = '{}, Accept-Encoding'.format(vary)
        else:
            response.headers['Vary'] = 'Accept-Encoding'

        return response

    def gz(self, response):
        compresslevel = self.app.config['COMPRESS_LEVEL'];
        if compresslevel > 9: compresslevel = 9;
        if compresslevel < 1: compresslevel = 1;
        out = gzip.compress(
            response.body,
            compresslevel=compresslevel)

        return out
