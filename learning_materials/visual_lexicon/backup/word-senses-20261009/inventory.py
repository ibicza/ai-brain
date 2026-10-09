"""Read saved catalogue and prepare lexical candidates; no Excel authoring/training."""
from pathlib import Path
import sys
import json
import importlib.util
import hashlib
import re

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, 'D:/ai-brain-data/visual-lexicon/tools/python-libs')
import pymorphy3

spec = importlib.util.spec_from_file_location('reader', REPO/'scripts/lexicon_catalogue_export.py')
reader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reader)
wb = REPO/'learning_materials/visual_lexicon/visual_lexicon.xlsx'
before = reader.sha(wb)
tables = reader.saved_tables(wb)
morph = pymorphy3.MorphAnalyzer()
records = []
for row in tables['Текст']['rows']:
    word = row[1]
    if not isinstance(word,str) or not re.fullmatch('[а-яё]+(?:-[а-яё]+)*', word):
        continue
    parses = morph.parse(word)
    top = parses[0]
    records.append({'text_id':row[0], 'lemma':word, 'forms':row[2], 'possible_ids':row[3],
                    'pdf_count':row[4], 'ocr_count':row[5], 'reason':row[8],
                    'sources':row[10], 'context':row[11], 'text_paths':row[12],
                    'pos':top.tag.POS, 'tag':str(top.tag), 'parse_score':top.score,
                    'known_dictionary_word':morph.word_is_known(word),
                    'alternative_parses':[{'lemma':p.normal_form,'tag':str(p.tag),'score':p.score} for p in parses[:4]]})
records.sort(key=lambda r:(-r['pdf_count'],-r['ocr_count'],r['lemma']))
root = Path('D:/ai-brain-data/visual-lexicon/word-senses-20261009')
root.mkdir(parents=True,exist_ok=True)
assert reader.sha(wb)==before
result={'input_workbook_sha256':before,'training_started':False,'training_admitted':False,
        'existing_words':tables['Словарь']['rows'], 'candidates':records,
        'limits':'Morphology proposes lemmas/parts of speech, not word senses or OCR correctness.'}
(root/'inventory.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
for group,parts in [('actions',{'VERB','INFN','PRTF','PRTS','GRND'}),('qualities_relations',{'ADJF','ADJS','COMP','ADVB','PREP','CONJ','PRCL','NPRO','PRED','INTJ','NUMR'}),('nouns',{'NOUN'})]:
    selected=[r for r in records if r['pos'] in parts and r['pdf_count']>=2 and r['known_dictionary_word']]
    (root/(group+'.json')).write_text(json.dumps(selected,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(group,len(selected),'; '.join(r['lemma'] for r in selected[:135]))
print('sha',before,'candidates',len(records))
