import copy
import json
from datetime import date
from pathlib import Path

import pytest
import requests
from PIL import Image

from stoxra.content import TOPICS, digest, review_digest, evidence_digest, topic_for, validate
from stoxra.pipeline import publish
from stoxra.render import render
from stoxra.services import Http, ServiceError, trusted_supabase, Instagram

DAY = date(2026, 1, 3)


@pytest.fixture
def post():
    return json.loads(Path('automation/examples/post.json').read_text())


@pytest.fixture
def facts():
    return json.loads(Path('automation/config/facts.json').read_text())


def test_calendar_rotates_all_topics():
    assert {topic_for(date(2026, 1, d)) for d in range(1, 8)} == set(TOPICS)


def test_valid_and_duplicate(post, facts):
    validate(post, facts, [], DAY)
    old = {'post': copy.deepcopy(post), 'digest': digest(post)}
    post['caption'] += ' Stay disciplined.'
    with pytest.raises(ValueError, match='Duplicate'):
        validate(post, facts, [old], DAY)


@pytest.mark.parametrize('bad', ['Guaranteed profits for everyone', 'Risk-free trading today', 'Earn ₹500 daily', 'Returns of 20%', 'Buy now for gains', 'Follow @scammer'])
def test_policy_rejects(post, facts, bad):
    post['caption'] = bad + '. Learn about trading today.'
    with pytest.raises(ValueError):
        validate(post, facts, [], DAY)


def test_expired_evidence(post, facts):
    with pytest.raises(ValueError, match='expired'):
        validate(post, facts, [], date(2028, 1, 1))


def test_unknown_evidence(post, facts):
    post['fact_ids'] = ['made-up']
    with pytest.raises(ValueError, match='Unknown'):
        validate(post, facts, [], DAY)


def test_template_and_live_logo(post, tmp_path):
    brand = json.loads(Path('automation/config/brand.json').read_text())
    brand['logo'] = str(tmp_path / 'absent.png')
    paths = render(post, brand, tmp_path)
    assert len(paths) == 2
    for path in paths:
        with Image.open(path) as image:
            assert image.size == (1080, 1350)
            assert image.format == 'JPEG'
    with pytest.raises(ValueError, match='logo'):
        render(post, brand, tmp_path, live=True)
    post['slides'][0]['title'] = 'W' * 60
    with pytest.raises(ValueError, match='Unbreakable'):
        render(post, brand, tmp_path)


class MemoryStore:
    def __init__(self):
        self.saved = []

    def verify_media(self, row):
        pass

    def save(self, row):
        self.saved.append(copy.deepcopy(row))


class FakeInstagram:
    def __init__(self, fail=False):
        self.publishes = 0
        self.created = 0
        self.fail = fail
        self.waits = []

    def preflight(self):
        pass

    def create_image(self, *args):
        self.created += 1
        return str(self.created)

    def create_carousel(self, children, caption):
        assert len(children) == 2
        return 'parent'

    def wait(self, container):
        self.waits.append(container)

    def publish(self, container):
        self.publishes += 1
        if self.fail:
            raise ServiceError('timeout')
        return 'instagram-id'


def row_for(post):
    row = {'post_key': 'test', 'account_id': '123', 'evidence_digest': evidence_digest(post, json.loads(Path('automation/config/facts.json').read_text())), 'media_hashes': ['hash-a', 'hash-b'], 'post': post, 'digest': digest(post), 'status': 'prepared',
            'approved_digest': digest(post), 'children': [], 'urls': ['https://example.com/a.jpg', 'https://example.com/b.jpg']}
    row['review_digest'] = review_digest(row)
    row['approved_digest'] = row['review_digest']
    return row


def test_carousel_idempotency(post, facts):
    row, store, ig = row_for(post), MemoryStore(), FakeInstagram()
    publish(row, store, ig, facts, DAY)
    assert row['instagram_post_id'] == 'instagram-id'
    assert store.saved[-2]['status'] == 'publishing'
    assert ig.waits[-1] == 'parent'
    publish(row, store, ig, facts, DAY)
    assert ig.publishes == 1


def test_uncertain_publish_never_retries(post, facts):
    row, store, ig = row_for(post), MemoryStore(), FakeInstagram(fail=True)
    with pytest.raises(ServiceError):
        publish(row, store, ig, facts, DAY)
    assert store.saved[-1]['status'] == 'publishing'
    with pytest.raises(ServiceError, match='Ambiguous'):
        publish(row, store, ig, facts, DAY)
    assert ig.publishes == 1


def test_approval_required_before_api(post, facts):
    row, ig = row_for(post), FakeInstagram()
    row['approved_digest'] = None
    with pytest.raises(ServiceError, match='approval'):
        publish(row, MemoryStore(), ig, facts, DAY)
    assert ig.created == 0


def test_resume_saved_containers(post, facts):
    row, ig = row_for(post), FakeInstagram()
    row['children'] = ['existing-a', 'existing-b']
    row['container_id'] = 'existing-parent'
    publish(row, MemoryStore(), ig, facts, DAY)
    assert ig.created == 0


class Session:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = 0

    def request(self, *args, **kwargs):
        self.calls += 1
        item = next(self.responses)
        if isinstance(item, Exception):
            raise item
        return item


def response(status, payload=None):
    r = requests.Response()
    r.status_code = status
    r._content = json.dumps(payload or {}).encode()
    return r


def test_rate_limit_read_retries():
    session = Session([response(429), response(200, {'ok': True})])
    sleeps = []
    assert Http(session, sleeps.append)('GET', 'https://example.com')['ok']
    assert len(sleeps) == 1


@pytest.mark.parametrize('failure', [response(500), response(429), requests.Timeout('secret-token')])
def test_mutation_never_retried(failure):
    session = Session([failure])
    with pytest.raises(ServiceError) as error:
        Http(session)('POST', 'https://example.com', retry=False)
    assert session.calls == 1
    assert 'secret-token' not in str(error.value)


@pytest.mark.parametrize('url', ['http://localhost', 'https://evil.com', 'https://a.supabase.co.evil.com', 'https://user@a.supabase.co', 'https://a.supabase.co/path'])
def test_storage_origin_restriction(url):
    with pytest.raises(ValueError):
        trusted_supabase(url)


def test_expiring_token_blocks_before_api(monkeypatch):
    for key, value in {'META_API_VERSION': 'v24.0', 'INSTAGRAM_ACCOUNT_ID': '123',
                       'INSTAGRAM_ACCESS_TOKEN': 'not-real', 'INSTAGRAM_TOKEN_EXPIRES_AT': '2020-01-01T00:00:00Z'}.items():
        monkeypatch.setenv(key, value)
    def forbidden(*a, **kw):
        pytest.fail('No request expected for expired token')
    with pytest.raises(ServiceError, match='Token'):
        Instagram(forbidden).preflight()


def test_approval_binds_visuals(post, facts):
    row = row_for(post)
    row['media_hashes'][0] = 'changed'
    with pytest.raises(ValueError, match='bundle integrity'):
        publish(row, MemoryStore(), FakeInstagram(), facts, DAY)


def test_single_image_publish(post, facts):
    post['slides'] = post['slides'][:1]
    row = row_for(post)
    row['urls'] = row['urls'][:1]
    row['media_hashes'] = row['media_hashes'][:1]
    row['review_digest'] = review_digest(row)
    row['approved_digest'] = row['review_digest']
    ig = FakeInstagram()
    publish(row, MemoryStore(), ig, facts, DAY)
    assert row['container_id'] == row['children'][0]
    assert ig.publishes == 1


def test_evidence_change_requires_review(post, facts):
    row = row_for(post)
    facts[0]['text'] = 'Changed editorial claim'
    with pytest.raises(ValueError, match='Evidence changed'):
        publish(row, MemoryStore(), FakeInstagram(), facts, DAY)


def test_lock_release_is_scoped_to_owner(monkeypatch):
    from stoxra.services import Store
    for key, value in {'PUBLISH_SUPABASE_URL': 'https://test.supabase.co',
                       'PUBLISH_SUPABASE_KEY': 'private', 'INSTAGRAM_ACCOUNT_ID': '123'}.items():
        monkeypatch.setenv(key, value)
    calls = []
    store = Store(lambda *args, **kw: calls.append((args, kw)))
    store.lock()
    store.unlock()
    assert calls[0][1]['retry'] is False
    assert calls[0][1]['json']['owner'] == store.lock_owner
    assert '&owner=eq.' + store.lock_owner in calls[1][0][1]


def test_api_container_and_alt_text_contract(monkeypatch):
    for key, value in {'META_API_VERSION': 'v24.0', 'INSTAGRAM_ACCOUNT_ID': '123',
                       'INSTAGRAM_ACCESS_TOKEN': 'private'}.items():
        monkeypatch.setenv(key, value)
    calls = []
    def fake(*args, **kwargs):
        calls.append((args, kwargs))
        return {'id': 'container'}
    ig = Instagram(fake)
    ig.create_image('https://example.com/a.jpg', 'Accessible description', child=True)
    args, kw = calls[-1]
    assert args[1] == 'https://graph.instagram.com/v24.0/123/media'
    assert kw['data']['is_carousel_item'] == 'true'
    assert kw['data']['alt_text'] == 'Accessible description'
    assert kw['headers']['Authorization'] == 'Bearer private'
    assert kw['retry'] is False
    ig.publish('container')
    assert calls[-1][1]['retry'] is False
