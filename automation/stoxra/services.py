import os
import hashlib
import uuid
import re
import time
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse, quote

import requests


class ServiceError(RuntimeError):
    pass


class Http:
    def __init__(self, session=None, sleep=time.sleep):
        self.session = session or requests.Session()
        self.sleep = sleep

    def __call__(self, method, url, *, retry=True, raw=False, **kwargs):
        for attempt in range(4):
            try:
                response = self.session.request(method, url, timeout=(10, 60), allow_redirects=False, **kwargs)
            except requests.RequestException:
                if not retry or attempt == 3:
                    raise ServiceError('Network failure; inspect durable state before retrying') from None
                self.sleep(2 ** attempt)
                continue
            if response.status_code == 429 or response.status_code >= 500:
                if retry and attempt < 3:
                    delay = response.headers.get('Retry-After', '')
                    self.sleep(min(60, int(delay)) if delay.isdigit() else 2 ** attempt)
                    continue
            if not 200 <= response.status_code < 300:
                # Never log body, URL, request headers or tokens.
                raise ServiceError(f'Service rejected request (HTTP {response.status_code})')
            if raw:
                return response
            return response.json() if response.content else None
        raise ServiceError('Retry budget exhausted')


def trusted_supabase(value):
    parsed = urlparse(value)
    if parsed.scheme != 'https' or not parsed.hostname or not parsed.hostname.endswith('.supabase.co') or parsed.path not in ('', '/') or parsed.username or parsed.port:
        raise ValueError('Use a hosted HTTPS project.supabase.co origin')
    return value.rstrip('/')


class Store:
    """Service-role-only records and public JPEG media; never public post metadata."""
    def __init__(self, http):
        self.http = http
        self.base = trusted_supabase(os.environ['PUBLISH_SUPABASE_URL'])
        self.headers = {'apikey': os.environ['PUBLISH_SUPABASE_KEY'],
                        'Authorization': 'Bearer ' + os.environ['PUBLISH_SUPABASE_KEY']}
        self.account = os.environ['INSTAGRAM_ACCOUNT_ID']
        self.lock_owner = str(uuid.uuid4())
        if not self.account.isdigit():
            raise ValueError('Invalid account ID')
        self.bucket = os.environ.get('PUBLISH_MEDIA_BUCKET', 'stoxra-media')
        if not re.fullmatch(r'[a-z0-9-]+', self.bucket):
            raise ValueError('Invalid bucket')

    def rest(self, method, path, **kw):
        return self.http(method, self.base + '/rest/v1/' + path, headers=self.headers, **kw)

    def lock(self):
        # No automatic lock expiry: process death must not allow a second publisher.
        self.rest('POST', 'stoxra_publish_locks', json={'account_id': self.account, 'owner': self.lock_owner}, retry=False)

    def unlock(self):
        self.rest('DELETE', 'stoxra_publish_locks?account_id=eq.' + self.account + '&owner=eq.' + self.lock_owner)

    def get(self, key):
        rows = self.rest('GET', 'stoxra_posts?post_key=eq.' + quote(key, safe=''))
        return rows[0] if rows else None

    def save(self, row, new=False):
        if new:
            self.rest('POST', 'stoxra_posts', json=row, retry=False)
        else:
            self.rest('PATCH', 'stoxra_posts?post_key=eq.' + quote(row['post_key'], safe=''), json=row)

    def history(self):
        return self.rest('GET', 'stoxra_posts?account_id=eq.' + self.account + '&order=created_at.desc&limit=200')

    def verify_media(self, row):
        if len(row['urls']) != len(row['media_hashes']):
            raise ValueError('Media hash count mismatch')
        prefix = self.base + f'/storage/v1/object/public/{self.bucket}/{self.account}/'
        for url, expected in zip(row['urls'], row['media_hashes']):
            if not url.startswith(prefix):
                raise ValueError('Untrusted media URL')
            data = self.http('GET', url, raw=True)
            if hashlib.sha256(data.content).hexdigest() != expected:
                raise ServiceError('Public media changed since review')

    def upload(self, path, key):
        object_key = f'{self.account}/{key}/{path.name}'
        self.http('POST', self.base + f'/storage/v1/object/{self.bucket}/{object_key}',
                  headers={**self.headers, 'Content-Type': 'image/jpeg', 'x-upsert': 'true'}, data=path.read_bytes())
        url = self.base + f'/storage/v1/object/public/{self.bucket}/{object_key}'
        response = self.http('GET', url, raw=True)
        if not response.headers.get('Content-Type', '').startswith('image/jpeg') or response.content[:2] != b'\xff\xd8':
            raise ServiceError('Public media JPEG preflight failed')
        return url


class Instagram:
    def __init__(self, http):
        self.http = http
        version = os.environ['META_API_VERSION']
        if not re.fullmatch(r'v\d+\.0', version):
            raise ValueError('META_API_VERSION must be explicitly selected, e.g. v24.0')
        self.base = 'https://graph.instagram.com/' + version + '/'
        self.account = os.environ['INSTAGRAM_ACCOUNT_ID']
        self.headers = {'Authorization': 'Bearer ' + os.environ['INSTAGRAM_ACCESS_TOKEN']}

    def call(self, method, path, **kw):
        return self.http(method, self.base + path, headers=self.headers, **kw)

    def preflight(self):
        expires = datetime.fromisoformat(os.environ['INSTAGRAM_TOKEN_EXPIRES_AT'].replace('Z', '+00:00'))
        if expires.tzinfo is None or expires < datetime.now(timezone.utc) + timedelta(days=7):
            raise ServiceError('Token expires within seven days or expiry is invalid; rotate token and secret')
        me = self.call('GET', 'me', params={'fields': 'user_id,username'})
        if str(me.get('user_id')) != self.account:
            raise ServiceError('Token account does not match configured professional account')
        limits = self.call('GET', self.account + '/content_publishing_limit', params={'fields': 'quota_usage,config'})
        data = limits['data'][0]
        if data['quota_usage'] >= data['config']['quota_total']:
            raise ServiceError('Instagram publishing quota exhausted')

    def create_image(self, url, alt_text, caption=None, child=False):
        data = {'image_url': url, 'alt_text': alt_text}
        if child:
            data['is_carousel_item'] = 'true'
        if caption is not None:
            data['caption'] = caption
        return self.call('POST', self.account + '/media', data=data, retry=False)['id']

    def create_carousel(self, children, caption):
        return self.call('POST', self.account + '/media', data={'media_type': 'CAROUSEL', 'children': ','.join(children), 'caption': caption}, retry=False)['id']

    def status(self, container):
        return self.call('GET', container, params={'fields': 'status_code'})['status_code']

    def wait(self, container):
        for _ in range(24):
            status = self.status(container)
            if status == 'FINISHED':
                return
            if status in ('ERROR', 'EXPIRED', 'PUBLISHED'):
                raise ServiceError('Container requires operator review: ' + status)
            time.sleep(5)
        raise ServiceError('Container readiness timed out; rerun resumes the saved container')

    def publish(self, container):
        # This mutation is NEVER automatically retried.
        return self.call('POST', self.account + '/media_publish', data={'creation_id': container}, retry=False)['id']
