"""Independent final payload QA; reads originals/corpus/workbook, writes only QA receipt."""
from pathlib import Path
import hashlib
import importlib.util
import json

REPO=Path('W:/toolbox_IDEA/programs/IdeaProjects/ai-brain')
QA=Path(__file__).parent
CORPUS=Path('D:/ai-brain-data/visual-lexicon/belarus-primary-20261009')
PASS2=Path('D:/ai-brain-data/visual-lexicon/book-review-pass2-20261009')
PAYLOAD=QA/'combined-prepared.json'
PRIOR=Path('D:/ai-brain-data/visual-lexicon/backups/visual_lexicon-da5dcd82aae6053d3ca736af48ccd57334419bb42dd14a85bef94dcdf53cb06b.xlsx')
OLD=Path('D:/ai-brain-data/visual-lexicon/merge-final-xml-safe.json')

def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def load(p):return json.loads(p.read_text(encoding='utf-8'))
def eq(a,b):return a==b or a in (None,'') and b in (None,'')

spec=importlib.util.spec_from_file_location('saved_reader',REPO/'scripts/lexicon_catalogue_export.py')
reader=importlib.util.module_from_spec(spec);spec.loader.exec_module(reader)
p=load(PAYLOAD);old=load(OLD)
assert sha(PRIOR)==p['input_workbook_sha256']
tables=reader.saved_tables(PRIOR)
keys={'Словарь':'words','Медиа':'media','Текст':'text','Покрытие':'coverage'}
counts={}
for sheet,key in keys.items():
    actual=tables[sheet]['rows'];counts[key]=len(actual)
    assert tables[sheet]['headers']==p[key+'_headers']==p['input_headers'][key]
    assert len(actual)==p['input_rows'][key]
    if key!='words':assert p[key][:len(actual)]==actual
    else:
        for before,after in zip(actual,p[key][:len(actual)],strict=True):
            assert before[:13]==after[:13]
            assert str(after[13] or '').startswith(str(before[13] or ''))
    assert len(old[key])==len(actual)
    assert all(all(eq(a,b) for a,b in zip(r[:13] if key=='words' else r,s[:13] if key=='words' else s,strict=True))
               for r,s in zip(old[key],actual,strict=True))
assert counts=={'words':460,'media':27523,'text':15499,'coverage':13}
assert len(p['words'])==847 and len(p['media'])==32526
assert p['text']==tables['Текст']['rows'] and p['coverage']==tables['Покрытие']['rows']
assert all(row[3]=='Не назначено' and row[15]=='Нет' for row in p['media'][counts['media']:])
assert p['training_started'] is False and p['training_admitted'] is False
assert p['spreadsheet_text_escapes'][:330]==old['spreadsheet_text_escapes']
assert all(r in p['review_files'] for r in old['review_files'])
assert p['previous_prepared_history']['saved_value_differences_preserved']==[]

manifest_path=REPO/'learning_materials/belarus_primary/manifest.json'
manifest=load(manifest_path)
originals={b['original_filename']:b for b in manifest['books']}
assert len(originals)==13
for b in originals.values():assert sha((manifest_path.parent/b['path']).resolve())==b['sha256']
overview=p['overview_coverage']['pages_by_book']
assert set(overview)==set(originals)
assert all(overview[name]==list(range(1,b['pages']+1)) for name,b in originals.items())
assert sum(map(len,overview.values()))==1763
assert p['stats']['pages_visually_reviewed']==84 and p['stats']['ocr_pages']==1763

replacements={r['page_id']:r for r in load(CORPUS/'geometry-corrections/replacement-index.json')['replacements']}
canon={}
for name,b in originals.items():
    for page in range(1,b['pages']+1):
        pid=b['sha256'][:16]+f'-p{page:04d}'
        relative=replacements.get(pid,{}).get('corrected_record',f'books/{b["sha256"][:16]}/records/{page:04d}.json')
        rpath=(CORPUS/relative).resolve();r=load(rpath)
        assert r['original_sha256']==b['sha256'] and r['original_filename']==name and r['pdf_page']==page and r['page_id']==pid
        if pid in replacements:assert sha(rpath)==replacements[pid]['corrected_record_sha256']
        preview=(CORPUS/r['page_preview']['path']).resolve()
        assert preview.is_relative_to(CORPUS) and sha(preview)==r['page_preview']['sha256']
        canon[(name,page)]={'path':str(preview),'sha':r['page_preview']['sha256']}

blocked=set()
for r in load(CORPUS/'effective-coverage-report.json')['superseded_unusable_media']:
    blocked.add(str((CORPUS/r['page_preview']['path']).resolve()))
    blocked.update(str((CORPUS/i['path']).resolve()) for i in r['images'])
verified={}
for row in p['media']:
    path=Path(row[2]).resolve()
    assert path.is_relative_to(CORPUS) or path.is_relative_to(PASS2)
    assert str(path) not in blocked and (not row[13] or str(Path(row[13]).resolve()) not in blocked)
    pair=(str(path),row[10])
    if pair not in verified:
        assert sha(path)==row[10];verified[pair]=True
for row in p['media'][counts['media']:]:
    assert row[4] in ('Сцена содержит объект','Страница содержит символ')
    name,remaining=row[7].split('; PDF ',1)
    page=int(remaining.split(';',1)[0])
    c=canon[(name,page)]
    assert str(Path(row[2]).resolve())==c['path']==str(Path(row[13]).resolve())
    assert row[10]==c['sha'] and row[9]==originals[name]['sha256'][:16]+f'-p{page:04d}'
    assert 'NOT_GOLD' in row[16]
for r in p['raw_assets']:
    path=Path(r['path']).resolve()
    assert path.is_relative_to(CORPUS) or path.is_relative_to(PASS2)
    assert sha(path)==r['sha256'] and str(path) not in blocked
for r in p['review_files']:
    path=Path(r['path']).resolve()
    assert path.is_relative_to(CORPUS) or path.is_relative_to(PASS2)
    assert sha(path)==r['sha256']
assert any('subtype uncertain' in r[6] and 'OBJ_2kl_Abroskina_rus_2024.pdf; PDF 62;' in r[7] for r in p['media'][counts['media']:])

for folder in ('math','world_language','language_safety'):
    review=load(PASS2/folder/'page-review.json')
    page_ids=[r['page_id'] for r in review['pages']]
    assert len(page_ids)==len(set(page_ids))

receipt={'status':'PASS','payload_path':str(PAYLOAD),'payload_sha256':sha(PAYLOAD),'prior_saved_workbook_sha256':sha(PRIOR),
 'input_rows':counts,'old_word_first13_exact_saved_values_preserved':True,'old_media_text_coverage_exact_saved_rows_preserved':True,
 'word_N_prefix_preserved_only_append':True,'previous_XML330_and6_reviews_preserved':True,'original_PDF_SHA_verified':13,
 'effective_page_previews_SHA_verified':len(canon),'overview_pages_exact_complete_union':1763,'detailed_pages_not_promoted':84,
 'all_current_media_SHA_confinement_verified':len(p['media']),'new_media_effective_page_identity_verified':len(p['media'])-counts['media'],
 'superseded_assets_excluded':True,'weak_pin_detail_flag_present':True,'training_started':False,'training_admitted':False,
 'limit':'Byte/source/page identity and saved-value checks; not independent resegmentation or verification of all labels/OCR semantics.'}
with (QA/'independent-payload-integrity.json').open('x',encoding='utf-8',newline='\n') as f:
    json.dump(receipt,f,ensure_ascii=False,indent=2);f.write('\n')
print(json.dumps(receipt))
