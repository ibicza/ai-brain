"""Build external immutable overview receipts from manually viewed pages; no OCR labeling, training, or corpus writes."""
import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path('D:/ai-brain-data/visual-lexicon/belarus-primary-20261009')
OUT = Path(__file__).parent
MERGE = Path('D:/ai-brain-data/visual-lexicon/merge-final-xml-safe.json')
REPO = Path('W:/toolbox_IDEA/programs/IdeaProjects/ai-brain')
FULL = {'0029feb5ba132920':[42], 'ddf715adede67a61':[86,101], '87b1e0db7b0b7831':[69], '56a1fad813b3bea7':[110,111]}
EXPECTED = {'0029feb5ba132920':118,'ddf715adede67a61':142,'87b1e0db7b0b7831':150,'56a1fad813b3bea7':150}
CANON = {'знак равно':'знак равенства','прямая':'прямая линия','кривая':'кривая линия','каштан':'каштан — плод',
 'лист':'лист растения','варежка':'варежки','ботинок':'ботинки','перчатка':'перчатки',
 'домино':'костяшка домино','люди':'человек','дети':'ребёнок','резинка':'ластик','краска':'краски',
 'ёлка':'ель','зубр':'европейский зубр','медведь игрушечный':'плюшевый медведь','набор красок':'краски'}
# New definitions are explicit proposals, not sense-resolved knowledge or training gold.
DEFS = {
 'девочка':'Ребёнок женского пола.', 'мальчик':'Ребёнок мужского пола.',
 'бабушка':'Женщина старшего поколения; бабушка ребёнка является матерью его родителя.',
 'дедушка':'Мужчина старшего поколения; дедушка ребёнка является отцом его родителя.',
 'ананас':'Тропический плод с жёсткой чешуйчатой кожурой и пучком листьев.',
 'банка':'Сосуд для хранения продуктов или других веществ.', 'банкнота':'Бумажный денежный знак определённого достоинства.',
 'бант':'Украшение из ленты, завязанной петлями.', 'баскетбольный мяч':'Мяч для игры в баскетбол.',
 'бегемот':'Крупное полуводное млекопитающее с массивным телом и широкой пастью.',
 'берег':'Край суши рядом с водоёмом.', 'божья коровка':'Небольшой жук, часто с пятнами на надкрыльях.',
 'бочка':'Округлая ёмкость для хранения и перевозки жидкостей или других веществ.',
 'будильник':'Часы с сигналом, подаваемым в установленное время.', 'будка':'Небольшое укрытие для собаки.',
 'булочка':'Небольшое хлебобулочное изделие.', 'бумага':'Тонкий листовой материал для письма, рисования и поделок.',
 'бумажный самолёт':'Сложенная из бумаги модель самолёта.', 'варенье':'Сладкий продукт из плодов или ягод, сваренных с сахаром.',
 'василёк':'Растение с цветочной корзинкой; распространённые полевые виды имеют синие цветки.',
 'ведро':'Сосуд с ручкой для переноски жидкости или сыпучих материалов.', 'веер':'Предмет для обмахивания, часто складывающийся.',
 'вертолёт':'Летательный аппарат с вращающимися несущими винтами.', 'весы':'Прибор для измерения массы.',
 'ветка':'Боковой побег дерева или кустарника.', 'воздушный змей':'Лёгкая конструкция, удерживаемая ветром в воздухе на нити.',
 'ворота':'Ограниченная рамой цель для попадания мяча в спортивной игре.',
 'восьмиугольник':'Многоугольник с восемью сторонами.', 'вышивка':'Узор, выполненный стежками на ткани.',
 'гвоздика':'Цветковое растение с узкими листьями и характерными бахромчатыми лепестками.',
 'гвоздь':'Заострённый крепёжный стержень, который обычно забивают молотком.',
 'гиря':'Груз определённой массы для весов или физических упражнений.', 'гитара':'Струнный музыкальный инструмент с корпусом и грифом.',
 'голубь':'Птица семейства голубиных.', 'горка':'Наклонная поверхность для катания; здесь детское игровое сооружение.',
 'горшок':'Сосуд; цветочный горшок служит для выращивания растений.',
 'гусеница':'Личинка бабочки, обычно с удлинённым телом и несколькими парами ног.',
 'дартс':'Игра с метанием дротиков в размеченную мишень.',
 'дорожный указатель':'Знак с названиями или стрелками, показывающий направления движения.',
 'доска':'Плоский деревянный материал; здесь строительная доска.', 'жёлудь':'Плод дуба с чашевидной шляпкой.',
 'забор':'Ограда, отделяющая участок территории.', 'здание':'Постройка с помещениями для людей или различных нужд.',
 'зерно':'Семя злакового растения.', 'иволга':'Певчая птица; самец обыкновенной иволги имеет ярко-жёлтое и чёрное оперение.',
 'измерительная лента':'Гибкая лента с делениями для измерения длины.', 'индюк':'Самец домашней индейки.',
 'кабачок':'Разновидность тыквы с продолговатым плодом, употребляемым как овощ.',
 'карусель':'Вращающееся устройство для катания.', 'карьерный самосвал':'Большой грузовой автомобиль для перевозки горных пород в карьере.',
 'катушка ниток':'Основа, на которую намотаны нитки.', 'кефир':'Кисломолочный напиток, полученный брожением молока.',
 'кирпич':'Строительный материал в форме небольшого блока.', 'клетка':'Ограждённое прутьями пространство для содержания животного.',
 'клоун':'Артист, использующий комические действия и характерный костюм.', 'клумба':'Участок земли, оформленный для выращивания цветов.',
 'колесо':'Круглая деталь, вращающаяся вокруг оси.', 'колокольчик':'Небольшой музыкальный предмет, издающий звон.',
 'комбайн':'Сельскохозяйственная машина, совмещающая несколько операций уборки урожая.',
 'компьютер':'Электронное устройство для обработки информации.', 'конфета':'Небольшое сладкое кондитерское изделие.',
 'копилка':'Ёмкость для накопления денег.', 'корзина':'Плетёная ёмкость для переноски или хранения вещей.',
 'коробка':'Ёмкость с жёсткими стенками для хранения или упаковки.',
 'краб':'Ракообразное с широким панцирем, клешнями и несколькими парами ног.',
 'ландыш':'Растение с широкими листьями и белыми цветками-колокольчиками на стебле.',
 'ласточка':'Небольшая птица с длинными крыльями и часто раздвоенным хвостом.',
 'лебедь':'Крупная водоплавающая птица с длинной шеей.', 'лента':'Длинная узкая полоса материала.',
 'лестница':'Устройство из ступеней для подъёма и спуска.',
 'лисичка гриб':'Съедобный гриб с жёлтой или оранжевой воронковидной шляпкой.',
 'ломаная':'Геометрическая линия из последовательно соединённых отрезков.',
 'лопата':'Инструмент с широкой рабочей частью для копания или перемещения материала.',
 'луч':'Часть прямой с начальной точкой, продолжающаяся неограниченно в одну сторону.',
 'магазин':'Место, где продаются товары.', 'мак':'Цветковое растение; многие виды имеют яркие лепестки и коробочку с семенами.',
 'малина':'Растение и его составной съедобный плод, образованный мелкими костянками.',
 'матрёшка':'Полая деревянная кукла, внутри которой помещаются меньшие подобные куклы.',
 'многоугольник':'Плоская фигура, ограниченная замкнутой ломаной.', 'мороженое':'Замороженный сладкий десерт.',
 'морская звезда':'Морское иглокожее животное с лучами, отходящими от центральной части тела.',
 'морской конёк':'Небольшая морская рыба с вертикальным телом и цепким хвостом.',
 'мука':'Порошкообразный продукт размалывания зерна или другого сырья.', 'мёд':'Сладкий продукт, производимый пчёлами из нектара или пади.',
 'обруч':'Кольцеобразный предмет, используемый для игр и гимнастики.',
 'орнамент':'Узор из повторяющихся элементов.', 'острый угол':'Угол меньше прямого угла, то есть меньше девяноста градусов.',
 'открытка':'Карточка с изображением или поздравлением.', 'пазл':'Изображение или конструкция, собираемые из отдельных взаимосвязанных частей.',
 'пакет':'Мягкая упаковка или сумка из бумаги, ткани либо полимерного материала.',
 'пальма':'Растение, обычно с неветвящимся стволом и крупными листьями на вершине.',
 'пальто':'Верхняя одежда, обычно длиннее куртки.', 'папка':'Предмет для хранения и упорядочивания листов бумаги.',
 'парашют':'Устройство с раскрывающимся куполом для замедления спуска в воздухе.',
 'паровоз':'Локомотив, использующий паровую машину.', 'парусник':'Судно, движущееся с помощью парусов.',
 'пенал':'Футляр для ручек, карандашей и других письменных принадлежностей.',
 'песочница':'Ограниченный участок с песком для детских игр.', 'пирамидка':'Игрушка из деталей, надеваемых на стержень или складываемых по размеру.',
 'пирог':'Выпечка из теста, часто с начинкой.', 'пирожное':'Небольшое сладкое кондитерское изделие, часто с кремом.',
 'пластилин':'Мягкий материал для лепки.', 'подарок':'Предмет, передаваемый другому человеку без оплаты.',
 'подсолнух':'Растение с крупной цветочной корзинкой, семена которого используют для получения масла.',
 'полоска':'Узкая вытянутая часть материала или изображённая область.', 'попугай':'Птица с изогнутым клювом; многие виды имеют яркое оперение.',
 'почтовая марка':'Небольшой знак оплаты почтового отправления.', 'пруд':'Небольшой водоём, обычно созданный или изменённый человеком.',
 'пуговица':'Небольшая деталь для застёгивания одежды или украшения.',
 'пчеловод':'Человек, занимающийся содержанием пчёл и получением продуктов пчеловодства.',
 'пятиугольник':'Многоугольник с пятью сторонами.', 'ракушка':'Твёрдая оболочка моллюска.',
 'редис':'Овощ с небольшим съедобным корнеплодом.', 'репа':'Овощное растение с округлым съедобным корнеплодом.',
 'саксофон':'Духовой музыкальный инструмент с тростью, клапанами и изогнутым раструбом.',
 'свёкла':'Растение со съедобным корнеплодом; столовая свёкла обычно имеет красно-фиолетовую мякоть.',
 'скакалка':'Верёвка с ручками для прыжков.', 'скамейка':'Длинное сиденье для нескольких людей.',
 'скворец':'Певчая птица с тёмным блестящим оперением, часто с мелкими светлыми пятнами.',
 'сковорода':'Посуда с плоским дном для жарки.', 'скрепка':'Изогнутая проволочная или пластиковая деталь для соединения листов бумаги.',
 'снеговик':'Фигура человека, слепленная из снега.', 'сноубордист':'Человек, катающийся на сноуборде.',
 'стрекоза':'Насекомое с удлинённым телом, крупными глазами и двумя парами крыльев.',
 'тележка':'Небольшое устройство на колёсах для перевозки груза.',
 'теннисная ракетка':'Спортивный предмет с ручкой и рамой со струнами для удара по теннисному мячу.',
 'теннисный мяч':'Небольшой упругий мяч для тенниса.', 'торт':'Кондитерское изделие, обычно из коржей с начинкой или кремом.',
 'трактор':'Самоходная машина для тяги и выполнения сельскохозяйственных или других работ.',
 'трамвай':'Городской транспорт, движущийся по рельсам.', 'троллейбус':'Автобус с электродвигателем, получающий питание через контактные провода.',
 'труба музыкальная':'Медный духовой инструмент с мундштуком и раструбом.',
 'тупой угол':'Угол больше прямого и меньше развёрнутого угла.',
 'турник':'Горизонтальная перекладина для физических упражнений.', 'тыква':'Растение и его крупный плод, употребляемый в пищу.',
 'тюльпан':'Луковичное растение с крупным цветком и широкими листьями.',
 'угольник':'Чертёжный инструмент треугольной формы для построения и проверки углов.',
 'улей':'Сооружение для содержания пчелиной семьи.', 'улитка':'Моллюск, обычно с раковиной и мягкой ползательной ногой.',
 'улица':'Пространство между рядами зданий с дорогой или проходом.',
 'флажок':'Небольшой флаг на древке или условный рисунок флага.',
 'фломастер':'Письменная принадлежность с пористым наконечником, пропитанным красящей жидкостью.',
 'фотоаппарат':'Устройство для получения фотографий.', 'футбольный мяч':'Мяч для игры в футбол.',
 'хоккеист':'Человек, играющий в хоккей.', 'цыплёнок':'Птенец курицы.',
 'чемодан':'Жёсткая или полужёсткая сумка для перевозки вещей.', 'черепаха':'Пресмыкающееся с панцирем.',
 'четырёхугольник':'Многоугольник с четырьмя сторонами.', 'шестиугольник':'Многоугольник с шестью сторонами.',
 'шляпа':'Головной убор с тульей и полями.', 'шоколад':'Кондитерский продукт на основе переработанных какао-бобов.',
 'щенок':'Детёныш собаки.', 'ястреб':'Хищная птица семейства ястребиных.',
 'сладкий перец':'Разновидность овощного перца с плодами без выраженной жгучести.',
 'чеснок':'Луковичное растение с луковицей из зубчиков, используемое как приправа.'
}

def read(p): return json.loads(p.read_text(encoding='utf-8'))
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def checked(asset):
    p=(ROOT/asset['path']).resolve()
    if not p.is_relative_to(ROOT.resolve()): raise ValueError('outside corpus')
    if sha(p)!=asset['sha256']: raise ValueError('SHA mismatch '+str(p))
    return str(p)
def save(name,obj):
    p=OUT/name
    if p.exists(): raise ValueError('immutable output already exists '+str(p))
    p.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return {'path':str(p),'sha256':sha(p),'bytes':p.stat().st_size}

obs=read(OUT/'observations.json'); catalog=read(MERGE); known={r[1]:r for r in catalog['words']}
contacts=[c for c in read(ROOT/'contact-sheets.json') if c['original_sha256'][:16] in EXPECTED]
replacements={r['page_id']:r for r in read(ROOT/'geometry-corrections/replacement-index.json')['replacements']}
pages=[]; concepts={}; unresolved={}; books=[]; seen_pages=set()
symbols={'цифры','рукописные цифры','буквы русского алфавита','вопросительный знак','скобки','стрелка','двоеточие'}
geometry={'круг','квадрат','треугольник','прямоугольник','ромб','трапеция','точка','прямая','кривая','отрезок','угол','луч','ломаная','параллелограмм','прямой угол','острый угол','тупой угол','многоугольник','четырёхугольник','пятиугольник','шестиугольник','восьмиугольник'}
notes={
 ('ddf715adede67a61',101):'FULL_PAGE: illustrated lower flowers are ландыш/василёк/ромашка/подснежник; neighbouring exercise names колокольчик/фиалка. Prose not used to override image.',
 ('ddf715adede67a61',86):'FULL_PAGE: lower replacement glyph is embroidered cloth, not a gnome; upper saxophones stylized. No clean gold.',
 ('87b1e0db7b0b7831',69):'FULL_PAGE labels visible: Воробей, Синица, Скворец, Иволга. Species labels contextual, not independent visual biological certification.',
 ('56a1fad813b3bea7',110):'FULL_PAGE: straw decorative figurines and ornamental crafts, not school supplies. Species/material details UNKNOWN.',
 ('56a1fad813b3bea7',111):'FULL_PAGE: bison depicted inside a jigsaw reproduction; not an isolated biological image.',
 ('0029feb5ba132920',42):'FULL_PAGE: vegetable grouping has carrots, courgettes, beetroot, peppers and garlic; containers/material details not inferred.'}
for c in contacts:
    cp=checked(c['media']); prefix=c['original_sha256'][:16]
    for n in c['pdf_pages']:
        pageid=f'{prefix}-p{n:04d}'; seen_pages.add((prefix,n))
        if str(n) not in obs[prefix]: raise ValueError('unviewed page '+pageid)
        rp=ROOT/'books'/prefix/'records'/f'{n:04d}.json'
        if pageid in replacements:
            r=replacements[pageid];rp=ROOT/r['corrected_record']
            if sha(rp)!=r['corrected_record_sha256']:raise ValueError('replacement seal mismatch')
        rec=read(rp)
        if rec['page_id']!=pageid or rec['pdf_page']!=n or rec['original_sha256']!=c['original_sha256']:raise ValueError('identity mismatch')
        preview=checked(rec['page_preview']); labels=obs[prefix][str(n)].split(';')
        inventory=[]
        for label in labels:
            if label in {'BLANK','TEXT_ONLY'}:continue
            word=CANON.get(label,label); role='page-contains-symbol' if label in symbols or label.startswith('знак ') or label in geometry else 'scene-contains-object'
            item={'observed_label':label,'role':role,'association_not_gold':True,'sense_confirmation':'OVERVIEW_PROPOSAL'}
            if word in known or word in DEFS:
                if word not in concepts:
                    row=known.get(word)
                    desc=row[2] if row else DEFS[word]
                    if len(desc.split())>20:raise ValueError('description too long '+word)
                    concept={'word':word,'description':desc,'category':row[3] if row else ('Геометрия' if label in geometry else 'Объект / понятие'), 'aliases':[], 'evidence':[]}
                    if row:concept['existing_id']=row[0]
                    concepts[word]=concept
                concept=concepts[word]
                if label!=word and label not in concept['aliases']:concept['aliases'].append(label)
                if 'existing_id' in concept:item['existing_id']=concept['existing_id']
                evidence={'filename':rec['original_filename'],'source_sha256':rec['original_sha256'],'pdf_page':n,'printed_page':None,
                    'page_id':pageid,'bbox_points':[0,0,*rec['page_size_points']], 'media_path':preview,'media_sha256':rec['page_preview']['sha256'],
                    'whole_page_path':preview,'whole_page_sha256':rec['page_preview']['sha256'],'role':role,'relation':'contains-object' if role=='scene-contains-object' else 'contains-symbol',
                    'split':'UNASSIGNED','training_admitted':False,'overview_only':n not in FULL[prefix],'single_object_crop':False,
                    'review_status':'AGENT_OVERVIEW_USER_PENDING','visible_text':None,
                    'notes':'Whole page context; spatial extent of object/symbol not segmented. No quantity/colour/sense truth or clean-control claim. '+notes.get((prefix,n),'')}
                concept['evidence'].append(evidence)
            else:
                item['identity_status']='UNKNOWN_EXACT_CONCEPT_OR_DEFINITION_PENDING'
                unresolved.setdefault(label,[]).append(pageid)
            inventory.append(item)
        pages.append({'page_id':pageid,'filename':rec['original_filename'],'source_sha256':rec['original_sha256'],'pdf_page':n,'printed_page':None,
            'effective_record_path':str(rp),'effective_record_sha256':sha(rp),'page_preview_path':preview,'page_preview_sha256':rec['page_preview']['sha256'],
            'contact_sheet_path':cp,'contact_sheet_sha256':c['media']['sha256'],'contact_pages':c['pdf_pages'],
            'overview_pixels_reviewed':True,'full_resolution_pixels_reviewed':n in FULL[prefix],
            'page_kind':labels[0] if labels[0] in {'BLANK','TEXT_ONLY'} else 'ILLUSTRATED_OR_SYMBOLIC',
            'inventory':inventory,'unresolved':['UNKNOWN exact fine text, individual numeric expressions/counts and unsegmented details'],
            'notes':notes.get((prefix,n),''),'split':'UNASSIGNED','training_admitted':False})
for prefix,count in EXPECTED.items():
    if {n for p,n in seen_pages if p==prefix}!=set(range(1,count+1)):raise ValueError('coverage gap')
    rec=next(x for x in pages if x['page_id'].startswith(prefix))
    original=REPO/'learning_materials/belarus_primary/originals'/rec['filename']
    if sha(original)!=rec['source_sha256']:raise ValueError('original SHA mismatch')
    books.append({'filename':rec['filename'],'source_sha256':rec['source_sha256'],'pages_overviewed':list(range(1,count+1)),
        'pages_full_resolution_reviewed':FULL[prefix],'object_segmentation_complete':False})
utc=datetime.now(timezone.utc).isoformat()
limitations=['All 560 pages viewed via 48 contact sheets; six additional wholepage previews checked. Not all pixels at original PDF render resolution.',
 'Not exhaustive object segmentation, clean controls, ontology truth, training or a blind model test.',
 'Generic/ambiguous labels such as digits, letters, stars, arrows retained in inventory, not assigned to arbitrary exact concepts.',
 'No OCR/prose-to-illustration automatic labels. Unknown fine detail stays UNKNOWN. Fullpage evidence relation only contains, not isolated object.']
pagefile=save('page-review.json',{'schema':1,'reviewer':'textbook_math_review','created_utc':utc,'catalogue_sha256':sha(MERGE),'observations_sha256':sha(OUT/'observations.json'),
 'books':books,'contact_sheets_verified':contacts,'pages':pages,'scope_limitations':limitations,'training_started':False})
annotationfile=save('supplemental-annotations.json',{'schema':1,'reviewer':'textbook_math_review_pass2','created_utc':utc,'books':books,'concepts':list(concepts.values()),
 'unresolved':[{'observed_label':k,'page_ids':v,'reason':'General class, ambiguous identity/role or definition pending; no exact concept admission.'} for k,v in unresolved.items()],
 'scope_limitations':limitations,'training_admitted':False})
save('receipt.json',{'schema':1,'reviewer':'textbook_math_review','created_utc':utc,'contacts_verified':len(contacts),'pages_overviewed':len(pages),
 'pages_full_resolution_reviewed':sum(map(len,FULL.values())),'concepts_linked_existing':sum('existing_id' in x for x in concepts.values()),
 'new_defined_proposals':sum('existing_id' not in x for x in concepts.values()),'occurrences':sum(len(x['evidence']) for x in concepts.values()),
 'unresolved_labels':len(unresolved),'files':[pagefile,annotationfile],'training_started':False,'training_admitted':False,'no_corpus_writes':True})
print(json.dumps({'pages':len(pages),'contacts':len(contacts),'concepts':len(concepts),'occurrences':sum(len(x['evidence']) for x in concepts.values()),'unresolved':len(unresolved)},ensure_ascii=False))
