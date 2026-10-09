"""Package reviewed lexical intermediates; never edit XLSX or train a model."""
from pathlib import Path
import gzip
import hashlib
import json
import shutil


ROOT = Path('D:/ai-brain-data/visual-lexicon/word-senses-20261009')
REPO = Path(__file__).resolve().parents[2]
OUTPUT = Path('D:/ai-brain-data/visual-lexicon/archives/word-senses-20261009')


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    if OUTPUT.exists():
        raise ValueError('Fresh archive destination required')
    OUTPUT.mkdir()
    inputs = [(ROOT / name, name, False) for name in (
        'actions-senses.json', 'nouns-senses.json', 'qualities-senses.json',
        'independent-review.json', 'independent-saved-xlsx-review.json')]
    inputs.extend([
        (ROOT / 'inventory.json', 'inventory.json.gz', True),
        (ROOT / 'publication/prepared.json', 'publication/prepared.json.gz', True),
        (REPO / 'tmp/visual-lexicon-words-20261009/inventory.py', 'inventory.py', False),
        (Path(__file__), 'backup_word_senses.py', False),
    ])
    inputs.extend((ROOT / 'publication/renders' / name, 'publication/renders/' + name, False)
                  for name in ('authoring-report.json', 'words.png', 'new-words.png',
                               'media.png', 'text.png', 'coverage.png'))
    manifest = []
    for source, relative, compressed in inputs:
        before = sha(source)
        target = OUTPUT / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if compressed:
            with source.open('rb') as src, target.open('xb') as dest:
                with gzip.GzipFile(filename='', mode='wb', fileobj=dest, mtime=0) as packed:
                    shutil.copyfileobj(src, packed)
            with gzip.open(target, 'rb') as restored:
                unpacked_sha = hashlib.file_digest(restored, 'sha256').hexdigest()
            if unpacked_sha != before:
                raise ValueError('Compressed content mismatch')
        else:
            shutil.copyfile(source, target)
            if sha(target) != before:
                raise ValueError('Copy mismatch')
        if sha(source) != before:
            raise ValueError('Input changed while packaging')
        manifest.append({
            'stored_path': relative,
            'restore_path': relative.removesuffix('.gz') if compressed else relative,
            'encoding': 'gzip' if compressed else 'bytes',
            'source_path': str(source),
            'source_sha256': before,
            'source_bytes': source.stat().st_size,
            'stored_sha256': sha(target),
            'stored_bytes': target.stat().st_size,
        })
    data = {
        'schema': 1,
        'archive_parent_commit': '22f6b470c7b7fe6034dc92553d2da1c593f41ef3',
        'baseline_workbook_sha256': '1472ce1acebdb56bc961879399193d7d6a05cbd405ab7a8c82b68694b1641a82',
        'published_workbook_sha256': '94f1c7b388b1c99daf053bd455d49640ce422292b669cfd6e98a71ee537b8c51',
        'training_started': False,
        'training_admitted': False,
        'files': manifest,
        'limits': 'Draft lexical senses; no occurrence labels, training or new mastery metrics. Canonical workbook/exports are archived at their stable repository paths; earlier corpus parts and pass2 review archive are reused.',
    }
    (OUTPUT / 'backup-manifest.json').write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'files': len(manifest), 'stored_bytes': sum(r['stored_bytes'] for r in manifest),
                      'manifest_sha256': sha(OUTPUT / 'backup-manifest.json')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
