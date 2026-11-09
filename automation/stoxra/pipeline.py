from .content import caption, digest, validate, review_digest, evidence_digest
from .services import ServiceError


def publish(row, store, instagram, facts, day, require_approval=True):
    if row['status'] == 'published':
        return row
    if row['status'] == 'publishing':
        # A timeout, crash or failed DB write may have happened after Meta accepted.
        raise ServiceError('Ambiguous publish: reconcile Meta media and saved container before any further publish')
    validate(row['post'], facts, [], day)
    if digest(row['post']) != row['digest']:
        raise ValueError('Stored post integrity mismatch')
    if row['evidence_digest'] != evidence_digest(row['post'], facts):
        raise ValueError('Evidence changed since draft; prepare and review a new bundle')
    if row['review_digest'] != review_digest(row):
        raise ValueError('Review bundle integrity mismatch')
    if require_approval and row.get('approved_digest') != row['review_digest']:
        raise ServiceError('Exact content digest needs human approval')
    store.verify_media(row)
    instagram.preflight()
    carousel = len(row['urls']) > 1
    if len(row['urls']) != len(row['post']['slides']):
        raise ValueError('Media count mismatch')
    for i, url in enumerate(row['urls']):
        if len(row['children']) <= i:
            child = instagram.create_image(url, row['post']['slides'][i]['alt_text'],
                                           None if carousel else caption(row['post']), carousel)
            row['children'].append(child)
            store.save(row)
        instagram.wait(row['children'][i])
    if not row.get('container_id'):
        row['container_id'] = instagram.create_carousel(row['children'], caption(row['post'])) if carousel else row['children'][0]
        row['status'] = 'container_ready'
        store.save(row)
    instagram.wait(row['container_id'])
    row['status'] = 'publishing'
    store.save(row)  # Must commit intent BEFORE the irreversible API call.
    row['instagram_post_id'] = instagram.publish(row['container_id'])
    row['status'] = 'published'
    store.save(row)
    return row
