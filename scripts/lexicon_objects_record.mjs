// Narrow, hash-guarded update of existing object-training records.
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';
import {getHeapStatistics} from 'node:v8';
import {spawnSync} from 'node:child_process';
const require = createRequire(import.meta.url);
const library = require.resolve('@oai/artifact-tool', {paths:[process.env.LEXICON_NODE_MODULES || process.cwd()]});
const {FileBlob,SpreadsheetFile,Workbook} = await import(pathToFileURL(library).href);
const [input, changesFile, output, qa, mode='edit'] = process.argv.slice(2);
assert(input && changesFile && output && qa);
assert(['preview','edit','verify','qa'].includes(mode));
// Exporting the large, unchanged media/text tables exceeds Node's default heap.
// Apply a process-only limit automatically; do not change OS memory settings.
if(mode==='edit' && getHeapStatistics().heap_size_limit < 6*1024**3){
  const child=spawnSync(process.execPath,['--max-old-space-size=8192',...process.argv.slice(1)],{stdio:'inherit'});
  if(child.error) throw child.error;
  process.exit(child.status ?? 1);
}
const sha = async p => crypto.createHash('sha256').update(await fs.readFile(p)).digest('hex');
const data = JSON.parse(await fs.readFile(changesFile,'utf8'));
const expectedInputSha=['verify','qa'].includes(mode)
  ? JSON.parse(await fs.readFile(path.join(qa,'authoring-report.json'),'utf8')).output_sha256
  : data.input_workbook_sha256;
assert.equal(await sha(input),expectedInputSha,'Saved workbook changed');
assert.equal(data.changes.length,8,'Exactly eight reviewed concepts');
assert.equal(new Set(data.changes.map(c=>c.id)).size,8);
assert.deepEqual(data.changes.map(c=>c.id).sort(),
  ['vc0175','vc0179','vc0186','vc0101','vc0114','vc0369','vc0158','vc0205'].sort(),
  'Unrelated concept update refused');
if(mode==='qa'){
  // Small disposable view of the independently verified saved records.
  // No QA worksheet/workbook is ever exported into the catalogue.
  const preservation=JSON.parse(await fs.readFile(path.join(path.dirname(changesFile),'saved-xlsx-preservation-extended.json'),'utf8'));
  assert.equal(preservation.candidate_sha256,expectedInputSha);
  assert.equal(preservation.all_other_cells_preserved,true);
  const prepared=JSON.parse(await fs.readFile(path.join(path.dirname(changesFile),'prepared.json'),'utf8'));
  const view=Workbook.create(); const sheet=view.worksheets.add('Проверка записей');
  sheet.getRange('A1:H9').values=[prepared.words_headers.slice(0,8),...data.changes.map(c=>c.after.slice(0,8))];
  sheet.getRange('A1:H1').format={fill:'#304866',font:{name:'Arial',size:10,bold:true,color:'#FFFFFF'},wrapText:true,rowHeight:48};
  sheet.getRange('A2:H9').format={font:{name:'Arial',size:10,color:'#253247'},wrapText:true,rowHeight:58,verticalAlignment:'top'};
  sheet.getRange('F2:F9').format.fill='#FCE8E6';
  sheet.getRange('G2:G9').setNumberFormat('0.0%');
  for(const [i,width] of [12,25,53,25,28,27,17,19].entries()) sheet.getRangeByIndexes(0,i,9,1).format.columnWidth=width;
  view.recalculate();
  const blob=await view.render({sheetName:sheet.name,range:'A1:H9',scale:1,format:'png'});
  await fs.writeFile(path.join(qa,'verified-object-records.png'),new Uint8Array(await blob.arrayBuffer()));
  assert.equal(await sha(input),expectedInputSha);
  console.log('Eight saved records visualized in a disposable QA view; original XLSX unchanged');
  process.exit(0);
}
const wb = await SpreadsheetFile.importXlsx(await FileBlob.load(input));
const words = wb.worksheets.getItem('Словарь');
const normal = v => v === undefined || v === '' ? null : v;
for(const change of data.changes){
  assert(Number.isInteger(change.row) && change.row>=9);
  assert.equal(change.before[0],change.id);
  assert.equal(change.after[0],change.id);
  assert.deepEqual(change.before.slice(0,5),change.after.slice(0,5),'Identity/meaning changed');
  assert.equal(change.before[13],change.after[13],'Unassigned book links changed');
  assert.equal(change.after[5],'Требует доработки');
  assert.equal(change.after[6],0);
  assert.equal(change.after[7],0);
  assert(change.after[12].startsWith(change.before[12] || ''),'Existing notes removed');
  const actual=words.getRange(`A${change.row}:N${change.row}`).values[0];
  assert.deepEqual(actual.map(normal),(mode==='verify'?change.after:change.before).map(normal),'Saved row differs');
  for(const value of change.after) assert(typeof value!=='string'||(value.length<=32767&&!value.startsWith('=')));
}
await fs.mkdir(qa,{recursive:true});
if(mode==='verify'){
  for(const change of data.changes){
    // Render the actual saved row in a disposable viewport near the header.
    // Some distant narrow ranges are omitted by the renderer. Never export
    // this QA-only in-memory copy or change the user's saved row positions.
    words.getRange('A9:H9').copyFrom(words.getRange(`A${change.row}:H${change.row}`),'all');
    const blob=await wb.render({sheetName:'Словарь',range:'A8:H10',scale:1,format:'png'});
    await fs.writeFile(path.join(qa,`${change.id}-snapshot.png`),new Uint8Array(await blob.arrayBuffer()));
  }
  assert.equal(await sha(input),expectedInputSha,'QA changed saved workbook');
  console.log('Saved object rows verified; disposable preview copies rendered, no file export');
  process.exit(0);
}
if(mode==='preview'){
  const first=data.changes[0].row;
  const blob=await wb.render({sheetName:'Словарь',range:`A${first}:H${first+1}`,scale:1,format:'png'});
  await fs.writeFile(path.join(qa,'before.png'),new Uint8Array(await blob.arrayBuffer()));
  console.log('Baseline rendered; no workbook edits');
  process.exit(0);
}
await fs.access(output).then(()=>{throw new Error('Fresh output required');},()=>{});
for(const change of data.changes) words.getRange(`F${change.row}:M${change.row}`).values=[change.after.slice(5,13)];
wb.recalculate();
console.log((await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!',options:{useRegex:true,maxResults:10},maxChars:1500})).ndjson);
for(const change of data.changes){
  assert.deepEqual(words.getRange(`A${change.row}:N${change.row}`).values[0].map(normal),change.after.map(normal));
}
assert.equal(await sha(input),data.input_workbook_sha256,'Workbook changed during editing');
await (await SpreadsheetFile.exportXlsx(wb)).save(output);
for(const change of data.changes){
  const blob=await wb.render({sheetName:'Словарь',range:`A${change.row}:H${change.row}`,scale:1,format:'png'});
  await fs.writeFile(path.join(qa,`${change.id}.png`),new Uint8Array(await blob.arrayBuffer()));
}
await fs.writeFile(path.join(qa,'authoring-report.json'),JSON.stringify({input_sha256:data.input_workbook_sha256,output_sha256:await sha(output),changed_concepts:data.changes.map(c=>c.id),object_training_started:true,object_gate:false,production_admitted:false},null,2));
console.log(JSON.stringify({output,sha256:await sha(output),changed_concepts:8}));
