"""Build the editable SVG architecture figures using only Python's standard library."""
from pathlib import Path
from html import escape

OUT = Path(__file__).resolve().parent / 'diagrams'
OUT.mkdir(parents=True, exist_ok=True)
INK='#172b46'; MUTED='#52647b'; LINE='#cbd5e1'
BLUE='#2253a0'; BRONZE='#986020'; SILVER='#34697b'; GOLD='#8a690c'

class Figure:
    def __init__(self,w,h,title,desc):
        self.w,self.h=w,h
        self.parts=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-labelledby="title desc">',
            f'<title id="title">{escape(title)}</title><desc id="desc">{escape(desc)}</desc>',
            '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#657892"/></marker></defs>',
            f'<rect width="{w}" height="{h}" fill="#f7f9fc"/>']
        self.text(42,46,title,30,INK,700)
        self.text(42,77,desc,17,MUTED)
    def text(self,x,y,t,size=18,color=INK,weight=400,mono=False):
        family='Consolas, monospace' if mono else 'Segoe UI, Arial, sans-serif'
        self.parts.append(f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}" font-weight="{weight}" fill="{color}">{escape(t)}</text>')
    def rect(self,x,y,w,h,fill='white',stroke=LINE,dash=False,r=12):
        d=' stroke-dasharray="7 5"' if dash else ''
        self.parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}" stroke="{stroke}" stroke-width="1.5"{d}/>')
    def card(self,x,y,w,h,title,lines,color=BLUE,pending=False):
        self.rect(x,y,w,h,stroke=color,dash=pending)
        self.parts.append(f'<path d="M{x+14} {y+1} H{x+w-14}" stroke="{color}" stroke-width="4"/>')
        self.text(x+18,y+34,title,21,color,700)
        for i,line in enumerate(lines): self.text(x+18,y+66+27*i,line,17,MUTED)
    def arrow(self,points,label=None,lx=None,ly=None):
        coords=' '.join(f'{x},{y}' for x,y in points)
        self.parts.append(f'<polyline points="{coords}" fill="none" stroke="#657892" stroke-width="2" stroke-linejoin="round" marker-end="url(#arrow)"/>')
        if label: self.text(lx,ly,label,15,MUTED)
    def save(self,name):
        self.parts.append('</svg>')
        (OUT/name).write_text('\n'.join(self.parts),encoding='utf-8')

f=Figure(1580,890,'01  Mobility lakehouse architecture','Target design • GAU and municipalities, 9–15 March 2023 • Layers are planned, not integrated')
xs=[42,350,658,966,1274]; w=264
for x,n,title,color in zip(xs,['01','02','03','04','05'],['SOURCES','BRONZE','SILVER','GOLD','CONSUMPTION'],[BLUE,BRONZE,SILVER,GOLD,BLUE]):
    f.text(x,135,f'{n}  {title}',20,color,700)
cards=[
 ('Public data', ['MITMA OD + exclusions','INE source datasets','Geographies: pending']),
 ('Raw evidence', ['Source-specific tables','Original values + lineage','File and batch manifest']),
 ('Conformed entities', ['Segmented OD trips','Zones, aliases, crosswalks','Indicators + pair distances']),
 ('Analytical products', ['Daily hourly OD totals','Comparable-day profiles','Gravity inputs + estimates']),
 ('Expert analysis', ['SQL and notebooks','Figures and clustering','Interpretation + review'])]
for i,(title,lines) in enumerate(cards):
    f.card(xs[i],165,w,170,title,lines,[BLUE,BRONZE,SILVER,GOLD,BLUE][i])
    if i<4:f.arrow([(xs[i]+w,248),(xs[i+1]-8,248)])
f.card(42,382,480,160,'Current executable evidence',['File selection and sample notebook','20 read-only terminal queries','Environment and DuckLake smoke checks'],BLUE)
f.card(550,382,480,160,'Integration still required',['Source readers and persistent tables','Zone / INE alignment and geometries','Reviewed transforms and quality checks'],SILVER,True)
f.card(1058,382,480,160,'Analytical limits',['One week is not an annual profile','District trips are from March 2022','No gravity ranking is validated'],GOLD,True)
f.rect(42,590,1496,100,'#eaf0f8',stroke='#d5dfed')
f.text(64,626,'PROCESSING  DuckDB executes SQL across the three layers',21,BLUE,700)
f.text(64,660,'STORAGE  DuckLake tables: local catalog + local data first; cloud deployment later',20,INK)
f.rect(42,714,1496,94,'white')
f.text(64,748,'CROSS-CUTTING CONTRACTS',18,INK,700)
f.text(64,780,'Provenance  /  source versions  /  coverage and rejects  /  safe join cardinality  /  rerun policy',20,MUTED)
f.text(42,852,'Solid boxes describe target components. Dashed boxes highlight pending dependencies or work.',16,MUTED)
f.save('01-lakehouse-overview.svg')

f=Figure(1500,870,'02  Bronze ingestion and provenance','Preserve the files and original values; make every loaded record traceable')
f.card(42,125,420,168,'1  Immutable source area',['MITMA CSV.gz and quality CSV','INE CSV, XLSX and ZIP member','Future geography sources'],BLUE)
f.card(540,125,420,168,'2  Source manifest',['Product + file hash + period','Expected schema and territorial level','Source version and reader contract'],BRONZE)
f.arrow([(462,208),(532,208)])
f.card(1038,125,420,168,'3  Source-specific readers',['Explicit headers, delimiters, encoding','Preserve codes, markers and units','Record member / sheet / row locator'],BRONZE)
f.arrow([(960,208),(1030,208)])
f.arrow([(1248,293),(1248,345),(750,345),(750,389)],'Parse with visible accounting',775,334)
f.card(42,395,420,202,'MITMA raw tables',['mitma_od_raw','mitma_quality_raw','Native product and source strings','No analytical aggregation'],BRONZE)
f.card(540,395,420,202,'INE raw table family',['ine_population_raw / ine_income_raw','ine_gdp_raw / ine_employment_raw','Native periods and categories','Different schemas remain separate'],BRONZE)
f.card(1038,395,420,202,'Geography raw tables',['zoning_raw / crosswalk_raw','Source geometry, version and CRS','Acquisition and readers pending','Retain authoritative identifiers'],BRONZE,True)
f.arrow([(750,366),(252,366),(252,389)])
f.arrow([(750,366),(1248,366),(1248,389)])
f.rect(42,633,1416,95,'#f7efe4',stroke='#dac6ac')
f.text(64,668,'RECORD LINEAGE',18,BRONZE,700)
f.text(64,702,'file hash + product + member / sheet + stable source locator  •  batch ID  •  load timestamp',20,INK)
f.text(42,777,'Load accounting: source records = loaded records + rejected records, under a documented counting rule.',19,INK)
f.text(42,814,'Same source identity and hash: skip a completed load. Corrected versions: replace only through an explicit reload policy.',17,MUTED)
f.save('02-bronze-ingestion.svg')

f=Figure(1580,1100,'03  Silver logical schema and join paths','Proposed keys and relationships • No geography or indicator join is assumed to be validated')
xs=[42,566,1090]; cw=448
f.card(xs[0],125,cw,190,'zone_aliases',['PK  source product + level + version','      + original zone value','FK  canonical zone key','Source labels remain in trip records'],SILVER)
f.card(xs[1],125,cw,190,'zones',['PK  level + zoning_version + zone_id','Name, geometry and centroid','Versioned coordinate system','One row per canonical zone'],SILVER)
f.card(xs[2],125,cw,190,'zone_crosswalk',['PK  zone key + geography key','      + mapping_version + validity','FK  zone / indicator geography','Weights only with a justified method'],SILVER)
f.arrow([(490,220),(558,220)],'N:1',507,207)
f.arrow([(1014,220),(1082,220)],'1:N',1031,207)
f.card(xs[0],410,cw,220,'od_trips',['ID  product + source record identity','Original origin / destination + segments','FK  origin zone / destination zone','trip_date, hour_slot and source level','trip_count, trip_km and quality status'],SILVER)
f.card(xs[1],410,cw,220,'od_distances',['PK  origin + destination zone keys','      + distance_method','distance_km, CRS and geometry version','Directed pair; intra-zone policy explicit','Only validated spatial distances'],SILVER)
f.card(xs[2],410,cw,220,'indicator_geographies',['PK  geography level + version + ID','Authoritative native INE geography','Province, municipality or other level','No inferred match by code similarity','Reference set / physical form proposed'],SILVER)
f.arrow([(180,410),(180,350),(714,350),(714,321)],'Two optional N:1 lookups after mapping',250,341)
f.arrow([(790,410),(790,321)],'Two N:1',806,369)
f.arrow([(1314,315),(1314,402)],'N:1',1329,365)
f.card(xs[0],732,cw,190,'quality_flags',['Event identity + source / row locator','Reason, scope and applicable period','Parse issue / exclusion / censoring','Quality events can affect many records'],SILVER)
f.card(xs[1],732,cw,190,'Safe enrichment contract',['Select indicator and category slice','Select one reference period / version','Check mapping and join cardinality','Reconcile trip totals after each join'],BLUE)
f.card(xs[2],732,cw,190,'ine_indicators',['PK  dataset + indicator + geography','      + period + categories + version','FK  native indicator geography','value + unit + source provenance'],SILVER)
f.arrow([(1314,732),(1314,638)],'N:1',1330,687)
f.arrow([(266,732),(266,638)],'Attach by declared scope',282,687)
f.text(42,983,'Zone key = (territorial level, zoning version, canonical zone ID); both OD endpoints carry the full key.',19,INK)
f.text(42,1020,'Aliases map source values to canonical zones. Crosswalks map canonical zones to native indicator geographies.',18,MUTED)
f.text(42,1054,'Do not join all indicators or all mapping versions to every trip. Geometry and alias resolution may remain nullable while pending.',17,MUTED)
f.save('03-silver-logical-schema.svg')

f=Figure(1500,970,'04  Gold analytical products and dependencies','Separate observed aggregations from estimates; preserve territorial level and analysis window')
f.text(42,135,'A  HOURLY MOBILITY PROFILES',21,GOLD,700)
xx=[42,414,786,1158]; ww=[312,312,312,300]
for i,(title,lines) in enumerate([
 ('Segmented OD trips',['Typed measures + quality flags','Original day, hour and segments','One territorial product at a time']),
 ('daily_od_hourly',['SUM segments per day / hour','Retain origin and destination','Reconcile trips with Silver']),
 ('Typical OD profile',['Average comparable daily totals','Count valid contributing days','Retain OD and sample window']),
 ('Zone hourly profile',['Daily departures / arrivals','Average valid comparable days','24-hour features; clustering later'])]):
    f.card(xx[i],163,ww[i],174,title,lines,GOLD)
    if i<2:f.arrow([(xx[i]+ww[i],248),(xx[i+1]-8,248)])
f.arrow([(570,337),(570,350),(1308,350),(1308,337)])
f.rect(42,365,1416,75,'#fbf6e7',stroke='#e2d3a3')
f.text(64,395,'AVERAGE CONTRACT',17,GOLD,700)
f.text(64,423,'Sum each day first. Define valid-day coverage; missing or censored observations are not automatically zero.',18,INK)
f.text(42,498,'B  GRAVITY INPUTS AND ESTIMATES',21,GOLD,700)
for i,(title,lines) in enumerate([
 ('Aligned input sources',['OD totals for one analysis window','Population + economic indicator','Zone-pair spatial distance']),
 ('gravity_inputs',['Validated geography mappings','Reference periods and units','Missing-data / coverage flags']),
 ('Calibration run',['k, economic proxy and window','Zero and intra-zone distance rules','Record parameters + run ID']),
 ('gravity_estimates',['Estimated vs observed demand','Ratio and coverage flags','Interpretation needs validation'])]):
    f.card(xx[i],527,ww[i],174,title,lines,GOLD,True)
    if i<3:f.arrow([(xx[i]+ww[i],611),(xx[i+1]-8,611)])
f.rect(42,736,1416,100,'white')
f.text(64,773,'estimated trips = k × population(origin) × economic proxy(destination) / distance_km²',21,INK,600)
f.text(64,808,'mismatch = estimated / observed trips, with an explicit policy for zero or missing observations',19,MUTED)
f.text(42,890,'Pending: geometries, source-to-zone aliases, INE alignment and model calibration. No infrastructure ranking is reported.',18,MUTED)
f.text(42,927,'The original third business question is still to be selected; its mart will follow a separate reviewed contract.',17,MUTED)
f.save('04-gold-products.svg')
print(f'Built four SVG diagrams in {OUT}')
