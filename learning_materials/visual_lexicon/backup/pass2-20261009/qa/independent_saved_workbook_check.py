"""Verify actual saved candidate values against payload and immutable input workbook."""
from pathlib import Path
import hashlib
import importlib.util
import json

QA=Path(__file__).parent
SOURCE=Path('W:/toolbox_IDEA/programs/IdeaProjects/ai-brain/scripts/lexicon_catalogue_export.py')
PRIOR=Path('D:/ai-brain-data/visual-lexicon/backups/visual_lexicon-da5dcd82aae6053d3ca736af48ccd57334419bb42dd14a85bef94dcdf53cb06b.xlsx')
candidate=QA/'visual_lexicon.xlsx';payload=QA/'combined-prepared.json'
def sha(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def eq(a,b):return a==b or a in (None,'') and b in (None,'')
spec=importlib.util.spec_from_file_location('independent_saved_reader',SOURCE)
reader=importlib.util.module_from_spec(spec);spec.loader.exec_module(reader)
before=sha(candidate)
actual=reader.saved_tables(candidate);original=reader.saved_tables(PRIOR)
p=json.loads(payload.read_text(encoding='utf8'))
keys={'Словарь':'words','Медиа':'media','Текст':'text','Покрытие':'coverage'}
counts={};compared=0
for sheet,key in keys.items():
    assert actual[sheet]['headers']==p[key+'_headers']
    assert actual[sheet]['tables'] and actual[sheet]['freeze']
    rows=actual[sheet]['rows'];counts[key]=len(rows)
    assert len(rows)==len(p[key])
    for n,(saved,wanted) in enumerate(zip(rows,p[key],strict=True)):
        assert len(saved)==len(wanted)
        for col,(a,b) in enumerate(zip(saved,wanted,strict=True)):
            assert eq(a,b),(sheet,n+9,col+1,str(a)[:100],str(b)[:100])
            compared+=1
    prior=original[sheet]['rows']
    if key=='words':
        assert len(prior)==460
        for old,new in zip(prior,rows[:460],strict=True):
            assert old[:13]==new[:13]
            assert str(new[13] or '').startswith(str(old[13] or ''))
    else:assert rows[:len(prior)]==prior
assert before==sha(candidate)
assert counts=={'words':847,'media':32526,'text':15499,'coverage':13}
assert all(r[3]=='Не назначено' and r[15]=='Нет' for r in actual['Медиа']['rows'][27523:])
assert sum(r[5] for r in actual['Покрытие']['rows'])==84
receipt={'status':'PASS','candidate_path':str(candidate),'candidate_sha256':before,'prepared_sha256':sha(payload),
 'prior_saved_workbook_sha256':sha(PRIOR),'saved_counts':counts,'all_saved_payload_cells_compared':compared,
 'native_tables_and_frozen_panes_preserved':True,'old_word460_first13_exact_saved_values_preserved':True,
 'old_media_text_coverage_exact_saved_values_preserved':True,'word_N_old_prefix_only_appended':True,
 'new_media_unassigned_unadmitted':True,'old_detailed_coverage84_not_promoted':True,
 'training_started':False,'limit':'Actual saved-value/schema integrity; no OCR/object-label semantic revalidation.'}
with (QA/'independent-saved-workbook-integrity.json').open('x',encoding='utf8',newline='\n') as f:
    json.dump(receipt,f,ensure_ascii=False,indent=2);f.write('\n')
print(json.dumps(receipt))
