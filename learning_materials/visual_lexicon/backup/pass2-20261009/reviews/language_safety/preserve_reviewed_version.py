"""Recover exact pre-flag annotation bytes; never rewrite independent crossreview."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).parent
current_path=ROOT/'supplemental-annotations.json'
current_bytes=current_path.read_bytes()
old=json.loads(current_bytes)
flag=' Независимый выборочный просмотр: мелкая группа игл/булавок, subtype uncertain; нужен увеличенный просмотр, не object gold.'
changes=[]
for concept in old['concepts']:
    for evidence in concept['evidence']:
        if flag in evidence['notes']:
            assert concept['word']=='булавка' and evidence['pdf_page']==62
            evidence['notes']=evidence['notes'].replace(flag,'')
            changes.append({'word':concept['word'],'filename':evidence['filename'],'pdf_page':62,'field':'notes','added':flag})
assert len(changes)==1
old_bytes=(json.dumps(old,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
old_sha=hashlib.sha256(old_bytes).hexdigest()
assert old_sha=='9b9d1c00bfd669c27d23685b099424c5995169c18d14f52c1ff32e31c4fc42cf'
current_sha=hashlib.sha256(current_bytes).hexdigest()
assert current_sha=='562734ee98aa0fe91432ee477a7c8dfe7468f1236b88c6bdfa2b0e6745def297'
with (ROOT/'annotations-before-pin-flag.json').open('xb') as f:f.write(old_bytes)
receipt={'before_sha256':old_sha,'after_sha256':current_sha,'changes_only':changes,
 'cross_review_path':str(ROOT.parent/'world_language/cross-review-language.json'),
 'cross_review_sha256':'1ae2505e39735db5df5fb0ff198781979182c1b94362719aca8f2eec8d99036f',
 'review_blind':False,'review_scope':'Independent selective read of nine full pages/eighteen proposed labels; not a blind generalisation test.',
 'training_admitted':False}
with (ROOT/'pin-flag-history-receipt.json').open('x',encoding='utf-8',newline='\n') as f:
    json.dump(receipt,f,ensure_ascii=False,indent=2);f.write('\n')
print(json.dumps({'before_sha256':old_sha,'after_sha256':current_sha,'changed_fields':1}))
