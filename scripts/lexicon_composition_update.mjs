// Append concept senses to the actual saved workbook, preserving old cells/features.
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';
const require=createRequire(import.meta.url);
const library=require.resolve('@oai/artifact-tool',{paths:[process.env.LEXICON_NODE_MODULES||process.cwd()]});
const {FileBlob,SpreadsheetFile}=await import(pathToFileURL(library).href);
const [input,prepared,output,qa,mode='preview']=process.argv.slice(2);
assert(['preview','edit'].includes(mode));
const sha=async p=>crypto.createHash('sha256').update(await fs.readFile(p)).digest('hex');
const data=JSON.parse(await fs.readFile(prepared,'utf8'));
assert.equal(await sha(input),data.input_workbook_sha256);
const wb=await SpreadsheetFile.importXlsx(await FileBlob.load(input));
const words=wb.worksheets.getItem('Словарь');
const count=data.input_rows.words;
const normalize=x=>x===undefined||x===''?null:x;
const before=words.getRangeByIndexes(8,0,count,14).values;
assert.deepEqual(before.map(r=>r.map(normalize)),data.words.slice(0,count).map(r=>r.map(normalize)));
await fs.mkdir(qa,{recursive:true});
if(mode==='preview'){
  const image=await wb.render({sheetName:'Словарь',range:'A8:F12',scale:1,format:'png'});
  await fs.writeFile(path.join(qa,'before.png'),new Uint8Array(await image.arrayBuffer()));
  assert.equal(await sha(input),data.input_workbook_sha256);
  console.log('Original catalogue rendered; no edits');
  process.exit(0);
}
await fs.access(output).then(()=>{throw Error('Fresh candidate required');},()=>{});
const additions=data.words.slice(count);
assert.equal(additions.length,27);
const table=words.tables.items.find(t=>t.name==='VisualConcepts');
assert(table);
table.rows.add(null,additions);
for(let i=0;i<additions.length;i++){
  const row=count+9+i;
  words.getRange(`A${row}:N${row}`).copyFrom(words.getRange(`A${count+8}:N${count+8}`),'all');
}
words.getRangeByIndexes(count+8,0,additions.length,14).values=additions;
const last=count+8+additions.length;
words.getRange(`F${count+9}:F${last}`).dataValidation={rule:{type:'list',values:['Запланировано','Сбор материалов','Материалы проверены','Обучается','Проверено на синтетике','Проверено на реальных','Требует доработки']}};
words.getRange(`G${count+9}:G${last}`).dataValidation={rule:{type:'decimal',operator:'between',formula1:0,formula2:1}};
words.getRange(`H${count+9}:H${last}`).dataValidation={rule:{type:'whole',operator:'greaterThanOrEqual',formula1:0}};
const media=wb.worksheets.getItem('Медиа');
const mediaCount=data.input_rows.media;
const oldMedia=media.getRangeByIndexes(8,0,mediaCount,19).values;
assert.deepEqual(oldMedia.map(r=>r.map(normalize)),data.media.slice(0,mediaCount).map(r=>r.map(normalize)));
const mediaAdditions=data.media.slice(mediaCount);
if(mediaAdditions.length){
  assert.equal(mediaAdditions.length,45);
  const mediaTable=media.tables.items.find(t=>t.name==='VisualMedia');
  assert(mediaTable);
  mediaTable.rows.add(null,mediaAdditions);
  for(let i=0;i<mediaAdditions.length;i++){
    const row=mediaCount+9+i;
    media.getRange(`A${row}:S${row}`).copyFrom(media.getRange(`A${mediaCount+8}:S${mediaCount+8}`),'all');
  }
  media.getRangeByIndexes(mediaCount+8,0,mediaAdditions.length,19).values=mediaAdditions;
  const mediaLast=mediaCount+8+mediaAdditions.length;
  media.getRange(`P${mediaCount+9}:P${mediaLast}`).dataValidation={rule:{type:'list',values:['Нет','Только процедурный эксперимент']}};
}
wb.recalculate();
assert.deepEqual(words.getRangeByIndexes(8,0,count,14).values.map(r=>r.map(normalize)),before.map(r=>r.map(normalize)));
assert.deepEqual(words.getRangeByIndexes(count+8,0,additions.length,14).values.map(r=>r.map(normalize)),additions.map(r=>r.map(normalize)));
assert.deepEqual(media.getRangeByIndexes(8,0,mediaCount,19).values.map(r=>r.map(normalize)),oldMedia.map(r=>r.map(normalize)));
console.log((await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#NUM!',options:{useRegex:true,maxResults:10},maxChars:1000})).ndjson);
assert.equal(await sha(input),data.input_workbook_sha256);
await (await SpreadsheetFile.exportXlsx(wb)).save(output);
// QA-only viewport copies, after export. Never publish these relocated rows.
for(const [offset,name] of [[0,'attributes'],[12,'animal-parts'],[21,'fruit-parts']]){
  words.getRange('A9:F13').copyFrom(words.getRangeByIndexes(count+8+offset,0,5,6),'all');
  const image=await wb.render({sheetName:'Словарь',range:'A8:F13',scale:1,format:'png'});
  await fs.writeFile(path.join(qa,name+'.png'),new Uint8Array(await image.arrayBuffer()));
}
await fs.writeFile(path.join(qa,'authoring-report.json'),JSON.stringify({baseline_sha256:data.input_workbook_sha256,candidate_sha256:await sha(output),appended_concepts:additions.length,existing_rows_preserved:true,production_admitted:false},null,2));
console.log(JSON.stringify({appended_concepts:additions.length,candidate_sha256:await sha(output)}));
