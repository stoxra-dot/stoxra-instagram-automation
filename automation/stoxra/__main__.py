import argparse
import hashlib
import json
import logging
import os
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .content import digest, generate, validate, verify, review_digest, evidence_digest
from .pipeline import publish
from .render import render
from .services import Http, Store, Instagram

logging.basicConfig(level=logging.INFO, format='%(message)s')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--mode', choices=['dry-run', 'prepare', 'publish', 'auto'], default='dry-run')
    p.add_argument('--date', default=datetime.now(ZoneInfo('Asia/Kolkata')).date().isoformat())
    p.add_argument('--example', type=Path)
    p.add_argument('--out', type=Path, default=Path('automation/output'))
    args = p.parse_args()
    day = date.fromisoformat(args.date)
    live = args.mode != 'dry-run'
    if live and args.example:
        p.error('Example fixtures are dry-run only')
    if live and os.environ.get('ENABLE_LIVE') != 'true':
        p.error('Live mode requires ENABLE_LIVE=true')
    if live and os.environ.get('EDITORIAL_BASELINE_APPROVED') != 'true':
        p.error('Owner must approve fact baseline before live mode')
    brand = json.loads(Path('automation/config/brand.json').read_text())
    facts = json.loads(Path('automation/config/facts.json').read_text())
    http = Http()
    store = Store(http) if live else None
    locked = False
    try:
        if store:
            store.lock()
            locked = True
        key = f'{store.account if store else "preview"}-{day.isoformat()}'
        row = store.get(key) if store else None
        if row and row['status'] == 'published':
            logging.info('Already published; no-op: %s', key)
            return
        if not row:
            if args.mode == 'publish':
                raise ValueError('Prepare content before publishing')
            history = store.history() if store else []
            post = json.loads(args.example.read_text()) if args.example else generate(http, day, facts, history)
            validate(post, facts, history, day)
            if not args.example:
                verify(http, post, [f for f in facts if f['id'] in post['fact_ids']])
            files = render(post, brand, args.out, live)
            row = {'post_key': key, 'account_id': store.account if store else 'preview',
                   'post': post, 'digest': digest(post), 'status': 'prepared', 'children': [],
                   'urls': [store.upload(f, digest(post)) for f in files] if store else [],
                   'evidence_digest': evidence_digest(post, facts),
                   'media_hashes': [hashlib.sha256(f.read_bytes()).hexdigest() for f in files],
                   'approved_digest': None, 'container_id': None, 'instagram_post_id': None}
            row['review_digest'] = review_digest(row)
            if store:
                store.save(row, new=True)
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / 'manifest.json').write_text(json.dumps(row, indent=2))
        if args.mode in ('publish', 'auto'):
            needs_approval = os.environ.get('REQUIRE_APPROVAL', 'true') != 'false'
            if args.mode == 'auto' and needs_approval and row.get('approved_digest') != row['review_digest']:
                logging.info('Prepared %s; awaiting exact-digest approval', key)
                return
            publish(row, store, Instagram(http), facts, day, needs_approval)
            (args.out / 'manifest.json').write_text(json.dumps(row, indent=2))
        logging.info('Completed mode=%s key=%s status=%s', args.mode, key, row['status'])
    finally:
        if locked:
            store.unlock()


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # Exceptions can contain secrets; log only the exception type.
        logging.error('Worker failed (%s); inspect durable state. No raw request data logged.', type(error).__name__)
        raise SystemExit(1) from None
