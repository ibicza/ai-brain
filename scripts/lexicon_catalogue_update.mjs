// Import the user's saved workbook; only extend the catalogue, never rebuild a seed.
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';
const require = createRequire(import.meta.url);
const library = require.resolve('@oai/artifact-tool', {
  paths: [process.env.LEXICON_NODE_MODULES || process.cwd()],
});
const {FileBlob, SpreadsheetFile} = await import(pathToFileURL(library).href);
const [input, prepared, output, qa] = process.argv.slice(2);
assert(input && prepared && output && qa, 'input.xlsx additions.json output.xlsx qa-directory');
const hash = async file => crypto.createHash('sha256').update(await fs.readFile(file)).digest('hex');
const data = JSON.parse(await fs.readFile(prepared, 'utf8'));
assert.equal(await hash(input), data.input_workbook_sha256, 'Saved input changed');
assert.equal(data.training_admitted, false);
assert.equal(data.training_started, false);
assert.equal(data.stats.effective_pages, 1763, 'Do not publish partial extraction as complete');
assert.equal(data.stats.ocr_pages, 1763, 'OCR must finish before publication');
assert.equal(data.stats.missing_ocr.length, 0);
await fs.access(output).then(() => {throw new Error('Output already exists; refuse overwrite');}, () => {});
await fs.mkdir(path.dirname(output), {recursive:true});
await fs.mkdir(qa, {recursive:true});
const wb = await SpreadsheetFile.importXlsx(await FileBlob.load(input));
console.log((await wb.inspect({kind:'workbook,sheet,table',maxChars:1700,tableMaxRows:1,tableMaxCols:3})).ndjson);
const words = wb.worksheets.getItem('Словарь');
const media = wb.worksheets.getItem('Медиа');
const oldWordCount = data.input_rows?.words ?? data.stats.concepts - data.stats.new_visual_concepts;
const oldWordWidth = data.input_headers?.words?.length ?? 13;
const oldWordRows = words.getRangeByIndexes(8,0,oldWordCount,oldWordWidth).values;
const oldMediaCount = data.input_rows?.media ?? data.media.length-data.stats.reviewed_occurrences-data.raw_assets.length;
assert(oldMediaCount>=0);
const oldMediaWidth = data.input_headers?.media?.length ?? 12;
const oldMediaRows = oldMediaCount ? media.getRangeByIndexes(8,0,oldMediaCount,oldMediaWidth).values : [];
const normal = v => v === '' || v === undefined ? null : v;
for (let i=0; i<oldWordRows.length; i++) {
  assert.deepEqual(oldWordRows[i].slice(0,13).map(normal), data.words[i].slice(0,13).map(normal), 'User word changed');
  if(oldWordWidth===14) assert(String(data.words[i][13]||'').startsWith(String(oldWordRows[i][13]||'')), 'Old unassigned links removed');
}
for (let i=0; i<oldMediaRows.length; i++) {
  assert.deepEqual(oldMediaRows[i].map(normal), data.media[i].slice(0,oldMediaWidth).map(normal), 'User media changed');
}
if(data.incremental) {
  for(const [name,key] of [['Словарь','words'],['Медиа','media'],['Текст','text'],['Покрытие','coverage']]) {
    const sheet=wb.worksheets.getItem(name);
    assert.deepEqual(sheet.getRangeByIndexes(7,0,1,data.input_headers[key].length).values[0],data.input_headers[key], 'Input schema changed');
    if(key==='text'||key==='coverage') assert.deepEqual(sheet.getRangeByIndexes(8,0,data.input_rows[key],data.input_headers[key].length).values.map(r=>r.map(normal)),data[key].slice(0,data.input_rows[key]).map(r=>r.map(normal)), 'Existing sheet edited by preparation');
  }
}
const literal = rows => rows.map(row => row.map(value => {
  assert(typeof value !== 'string' || value.length <= 32767, 'Excel string too long');
  return typeof value === 'string' && value.startsWith('=') ? "'"+value : value;
}));
const statuses = ['Запланировано','Сбор материалов','Материалы проверены','Обучается','Проверено на синтетике','Проверено на реальных','Требует доработки'];
const header = {fill:'#304866',font:{name:'Arial',size:10,bold:true,color:'#FFFFFF'},wrapText:true,horizontalAlignment:'center',verticalAlignment:'center',rowHeight:48};
const body = {font:{name:'Arial',size:10,color:'#253247'},wrapText:true,verticalAlignment:'top',rowHeight:58};
function title(sheet, text, instructions) {
  sheet.getRange('A2').values = [[text]];
  sheet.getRange('A2').format.font = {name:'Arial',size:14,bold:true,color:'#253247'};
  sheet.getRange('A2').format.rowHeight = 26;
  for (let i=0;i<instructions.length;i++) sheet.getRange(`A${i+3}`).values = [[instructions[i]]];
  sheet.showGridLines = false;
  sheet.freezePanes.freezeRows(8);
  sheet.freezePanes.freezeColumns(2);
}
function table(sheet, name, headers, rows, widths, existing=false, oldCount=0) {
  console.log(`Writing ${name}: ${rows.length} rows`);
  const last=rows.length+8;
  if(data.incremental && existing) {
    const native=sheet.tables.items.find(t=>t.name===name);
    assert(native,'Missing expected native table');
    if(rows.length>oldCount) native.rows.add(null,literal(rows.slice(oldCount)));
    if(name==='VisualConcepts') sheet.getRangeByIndexes(8,13,oldCount,1).values=literal(rows.slice(0,oldCount).map(r=>[r[13]]));
    if(rows.length>oldCount) sheet.getRangeByIndexes(8+oldCount,0,rows.length-oldCount,headers.length).format=body;
    console.log(`Completed append-only ${name}`);
    return last;
  }
  if (existing) sheet.tables.items.find(t=>t.name===name).delete();
  sheet.getRangeByIndexes(7,0,rows.length+1,headers.length).values = literal([headers,...rows]);
  let end=''; let number=headers.length;
  while(number>0){number--;end=String.fromCharCode(65+number%26)+end;number=Math.floor(number/26);}
  sheet.tables.add(`A8:${end}${last}`, true, name).showFilterButton=true;
  sheet.getRangeByIndexes(7,0,1,headers.length).format=header;
  if (!existing || name==='VisualMedia') sheet.getRangeByIndexes(8,0,rows.length,headers.length).format=body;
  else {
    // Preserve original styles; style only appended rows and the new column.
    sheet.getRangeByIndexes(8+oldWordRows.length,0,rows.length-oldWordRows.length,headers.length).format=body;
    sheet.getRangeByIndexes(8,13,oldWordRows.length,1).format=body;
  }
  for(let i=0;i<widths.length;i++) sheet.getRangeByIndexes(7,i,1,1).format.columnWidth=widths[i];
  console.log(`Completed ${name}`);
  return last;
}
title(words, 'Визуальный словарь — постоянный каталог', [
  `2026-10-09. Разбор 13 учебников; обзор страниц: ${data.stats.overview_pages??0}/1763. Разметка — предложения, не знание модели.`,
  'Пустой процент = отдельного измерения нет. Старые результаты и ID сохранены без повышения статуса.',
  'Новые картинки находятся в колонке N: разбиение пока не назначено. Полный текст и сомнения — на листе «Текст».',
  'Правьте этот сохранённый файл. Новый смысл = новый ID. Обучение по учебникам не запускалось.',
]);
const wordLast=table(words,'VisualConcepts',data.words_headers,data.words,[12,25,53,25,28,27,17,19,38,38,39,40,57,52],true,oldWordCount);
words.getRange(`F9:F${wordLast}`).dataValidation={rule:{type:'list',values:statuses}};
words.getRange(`G9:G${wordLast}`).dataValidation={rule:{type:'decimal',operator:'between',formula1:0,formula2:1}};
words.getRange(`G9:G${wordLast}`).setNumberFormat('0.0%');
words.getRange(`H9:H${wordLast}`).dataValidation={rule:{type:'whole',operator:'greaterThanOrEqual',formula1:0}};
title(media,'Медиафайлы и происхождение',[
  'Одна строка — ресурс или связь файла с понятием; растровое размещение не равно отдельному предмету.',
  'Все исходные страницы сохранены. Оговорки независимого чтения, надписи-подсказки и повторные сцены отмечены.',
  'Нет допуска обучения. Пользователь ещё не подтвердил предложенные подписи; сырые ресурсы — черновики.',
  'Связанные сцены и дубли нельзя разделять между обучением и контролем. Регрессия не является новым слепым экзаменом.',
]);
const mediaLast=table(media,'VisualMedia',data.media_headers,data.media,[16,13,45,20,25,25,65,56,31,36,40,30,38,45,28,18,42,18,32],true,oldMediaCount);
media.getRange(`D9:D${mediaLast}`).dataValidation={rule:{type:'list',values:['Не назначено','train','dev','calibration','regression','fresh_final']}};
media.getRange(`L9:L${mediaLast}`).dataValidation={rule:{type:'list',values:['Черновик','Агент проверил; ожидает пользователя','Агент предложил; ожидает пользователя','Проверено','Карантин']}};
const roleChoices=[...new Set(data.media.map(r=>r[4]).filter(v=>typeof v==='string'&&v))];
if(roleChoices.join(',').length<=255) media.getRange(`E9:E${mediaLast}`).dataValidation={rule:{type:'list',values:roleChoices}};
media.getRange(`P9:P${mediaLast}`).dataValidation={rule:{type:'list',values:['Нет']}};
const text = data.incremental ? wb.worksheets.getItem('Текст') : wb.worksheets.add('Текст');
title(text,'Слова и формы из полного текста',[
  'Все страницы: текст PDF + Windows OCR. Ошибки распознавания, имена и неоднозначные значения требуют проверки.',
  'Возможный ID — только совпадение написания/леммы, не доказательство смысла. Слова и картинки не склеиваются вслепую.',
  'Числа, знаки и исходные строки не удалены: они сохранены в полном тексте и OCR-файлах на листе «Медиа».',
  'PDF и OCR перекрываются. Служебные символы показаны как \\uXXXX; исходный текст сохранён без изменений.',
]);
table(text,'TextCandidates',data.text_headers,data.text,[18,25,45,24,20,18,14,37,42,53,60,70,50],!!data.incremental,data.input_rows?.text??0);
const coverage=data.incremental ? wb.worksheets.getItem('Покрытие') : wb.worksheets.add('Покрытие');
title(coverage,'Покрытие и границы проверки',[
  'Сохранены все 1763 страницы 13 книг. Автоматическое извлечение не заменяет семантическую проверку иллюстраций.',
  `Обзор: ${data.stats.overview_pages??0}/1763 страниц. Колонка F сохраняет первый детальный проход (84); это разные уровни проверки.`,
  '13 геометрических исправлений заменяют целые записи страниц; старые ресурсы явно исключены из текущего каталога.',
  'Нет обучения, новых метрик модели или полностью подтверждённого человеком учебного корпуса.',
]);
table(coverage,'BookCoverage',data.coverage_headers,data.coverage,[63,40,18,21,18,24,23,20,85],!!data.incremental,data.input_rows?.coverage??0);
wb.recalculate();
console.log((await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!',options:{useRegex:true,maxResults:10},maxChars:1500})).ndjson);
console.log((await wb.inspect({kind:'table',range:'Словарь!A8:H11',include:'values,formulas',tableMaxRows:4,tableMaxCols:8,maxChars:1800})).ndjson);
assert.equal(await hash(input),data.input_workbook_sha256,'Saved input changed before export');
console.log('Exporting verified matrices');
try {
  await (await SpreadsheetFile.exportXlsx(wb)).save(output);
} catch(error) {
  console.error('XLSX export failed:', String(error.message || error).slice(0,2000));
  process.exit(1);
}
console.log('XLSX saved; rendering four-sheet QA');
await fs.writeFile(path.join(qa,'authoring-report.json'),JSON.stringify({input_sha256:data.input_workbook_sha256,output_sha256:await hash(output),stats:data.stats,training_started:false,qa_completed:false},null,2));
for (const [sheetName,range,name] of [
  ['Словарь','A8:F13','words.png'],['Словарь',`A${wordLast-4}:F${wordLast}`,'new-words.png'],
  ['Медиа','B8:H12','media.png'],['Текст','A8:J12','text.png'],['Покрытие','A8:F12','coverage.png'],
]) {
  const image = await wb.render({sheetName,range,scale:1,format:'png'});
  await fs.writeFile(path.join(qa,name),new Uint8Array(await image.arrayBuffer()));
}
await fs.writeFile(path.join(qa,'authoring-report.json'),JSON.stringify({input_sha256:data.input_workbook_sha256,output_sha256:await hash(output),stats:data.stats,training_started:false,qa_completed:true},null,2));
console.log(JSON.stringify({output,sha256:await hash(output),stats:data.stats}));
