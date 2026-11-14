import json, os, re, threading, time, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT=Path(__file__).parent
CACHE={"at":0,"data":None}
LOCK=threading.Lock()
FMI="https://opendata.fmi.fi/wfs"
SEA={"pietarsaari":"134250","raahe":"100540"}
WEATHER={"tankar":{"fmisid":"101661"},"ulkokalla":{"fmisid":os.getenv("ULKOKALLA_FMISID","")}}
def stamp(dt): return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
def fetch(query, station=None, place=None, hours=30, timestep=60):
    now=datetime.now(timezone.utc)
    p={"service":"WFS","version":"2.0.0","request":"getFeature",
       "storedquery_id":query,"starttime":stamp(now-timedelta(hours=hours)),
       "endtime":stamp(now),"timestep":str(timestep)}
    if station: p["fmisid"]=station
    if place: p["place"]=place
    url=FMI+"?"+urllib.parse.urlencode(p)
    with urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"PerameriSeuranta/1.0"}),timeout=18) as resp:
        raw=resp.read(5_000_000)
    root=ET.fromstring(raw)
    errors=[(e.text or "") for e in root.iter() if e.tag.split("}")[-1] in ("ExceptionText","ServiceException")]
    if errors: raise ValueError("; ".join(errors)[:250])
    records={}
    for e in root.iter():
        if e.tag.split("}")[-1] != "BsWfsElement": continue
        item={}
        for child in e.iter():
            tag=child.tag.split("}")[-1]
            if tag in ("Time","ParameterName","ParameterValue","LocationName"): item[tag]=(child.text or "").strip()
        if item.get("Time") and item.get("ParameterName") and item.get("ParameterValue"):
            try:
                value=float(item["ParameterValue"])
                if value==value and abs(value)<100000:
                    records.setdefault(item["Time"],{})[item["ParameterName"].lower()]=value
            except ValueError: pass
    return [{"time":t,**v} for t,v in sorted(records.items())]
def pick(rec,names):
    for name in names:
        if name in rec: return rec[name]
    return None
def sea_value(r):
    # FMI's sea-level field varies by dataset; prefer instant/mean water level fields.
    names=[k for k in r if k!="time" and ("wlev" in k or "sealevel" in k or "sea_level" in k)]
    if not names:
        names=[k for k in r if k!="time" and ("waterlevel" in k or "vedenkorkeus" in k)]
    names=sorted(names,key=lambda k:(0 if "instant" in k else 1 if "avg" in k else 2,k))
    return r[names[0]] if names else None
def latest(series, getter):
    for row in reversed(series):
        value=getter(row)
        if value is not None: return {"value":round(value,2),"time":row["time"]}
    return {"value":None,"time":None}

def fetch_waves():
    # FMI's documented wave timevaluepair query, Perämeri buoy FMISID 137228.
    now=datetime.now(timezone.utc)
    p={"service":"WFS","version":"2.0.0","request":"getFeature",
       "storedquery_id":"fmi::observations::wave::timevaluepair","fmisid":"137228",
       "starttime":stamp(now-timedelta(hours=36)),"endtime":stamp(now)}
    url=FMI+"?"+urllib.parse.urlencode(p)
    with urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"PerameriSeuranta/1.1"}),timeout=22) as resp:
        root=ET.fromstring(resp.read(5000000))
    for e in root.iter():
        if e.tag.split("}")[-1] in ("ExceptionText","ServiceException"):
            raise ValueError((e.text or "FMI WFS virhe")[:200])
    results=[]
    temps=[]
    for member in root.iter():
        if member.tag.split("}")[-1] != "member": continue
        property_links=[]
        for e in member.iter():
            if e.tag.split("}")[-1] == "observedProperty":
                property_links.extend(v.lower() for v in e.attrib.values())
        is_height=any("wavehs" in x for x in property_links)
        is_temp=any(("watertemperature" in x or "water_temperature" in x or "seatemp" in x or "sea_temperature" in x or "wavetw" in x) for x in property_links)
        if not (is_height or is_temp): continue
        for point in member.iter():
            if point.tag.split("}")[-1] not in ("MeasurementTVP","TimeValuePair"): continue
            t=v=None
            for e in point.iter():
                key=e.tag.split("}")[-1]
                if key=="time": t=(e.text or "").strip()
                elif key=="value":
                    try: v=float((e.text or "").strip())
                    except ValueError: pass
            if t and v is not None and v==v:
                if is_height and 0<=v<30: results.append({"time":t,"value":round(v,2)})
                if is_temp and -3<=v<40: temps.append({"time":t,"value":round(v,2)})
    results.sort(key=lambda x:x["time"])
    temps.sort(key=lambda x:x["time"])
    return results,temps

def collect():
    data={"updated":stamp(datetime.now(timezone.utc)),"sea":{},"weather":{},"errors":{},"series":{},"source":"Ilmatieteen laitos / FMI avoin data"}
    for name,sid in SEA.items():
        try:
            raw=fetch("fmi::observations::mareograph::simple",station=sid,hours=48,timestep=60)
            points=[{"time":r["time"],"value":sea_value(r)} for r in raw if sea_value(r) is not None]
            data["sea"][name]=latest(points,lambda r:r["value"])
            data["series"][name]=points
            if not points: data["errors"][name]="Merivedenkorkeuden havaintoja ei löytynyt FMI-vastauksesta."
        except Exception as e:
            data["sea"][name]={"value":None,"time":None}
            data["series"][name]=[]
            data["errors"][name]=str(e)
    for name,station in WEATHER.items():
        sid=station["fmisid"]
        if not sid:
            data["weather"][name]=None
            data["errors"][name]="Ulkokallan FMI-asematunnusta ei ole vahvistettu. Aseta ULKOKALLA_FMISID."
            continue
        try:
            rows=fetch("fmi::observations::weather::simple",station=sid,hours=3,timestep=10)
            fields={"temperature":["t2m","temperature"],"wind":["ws_10min","windspeedms"],"gust":["wg_10min","windgust"],"direction":["wd_10min","winddirection"],"humidity":["rh","humidity"]}
            output={}
            for label,aliases in fields.items(): output[label]=latest(rows,lambda r:pick(r,aliases))
            data["weather"][name]=output
            if not any(x["value"] is not None for x in output.values()):
                data["errors"][name]="Sääaseman havaintoja ei löytynyt."
        except Exception as e:
            data["weather"][name]=None
            data["errors"][name]=str(e)
    try:
        waves,water_temp=fetch_waves()
        data["waves"]={"station":"Perämeri aaltopoiju","height":latest(waves,lambda x:x["value"]),"unit":"m"}
        data["water_temperature"]={"station":"Perämeren aaltopoiju","temperature":latest(water_temp,lambda x:x["value"]),"unit":"°C"}
        if not water_temp: data["errors"]["water_temperature"]="Veden lämpötilahavaintoa ei löydy aallokkohavaintojen vastauksesta."
        if not waves: data["errors"]["waves"]="Aallonkorkeushavaintoja ei saatavilla (esimerkiksi jääkausi)."
    except Exception as e:
        data["waves"]={"station":"Perämeri aaltopoiju","height":{"value":None,"time":None},"unit":"m"}
        data["errors"]["waves"]=str(e)
        data["water_temperature"]={"station":"Perämeren aaltopoiju","temperature":{"value":None,"time":None},"unit":"°C"}
    return data
class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs): super().__init__(*args,directory=str(ROOT),**kwargs)
    def do_GET(self):
        if self.path.startswith("/api/data"):
            try:
                with LOCK:
                    if time.time()-CACHE["at"]>600 or CACHE["data"] is None:
                        CACHE["data"]=collect()
                        CACHE["at"]=time.time()
                    data=CACHE["data"]
                body=json.dumps(data,ensure_ascii=False).encode()
                self.send_response(200)
            except Exception as e:
                body=json.dumps({"error":str(e)}).encode()
                self.send_response(502)
            self.send_header("Content-Type","application/json; charset=utf-8")
            self.send_header("Cache-Control","no-store")
            self.send_header("Content-Length",str(len(body)))
            self.end_headers();self.wfile.write(body)
        else: super().do_GET()
if __name__=="__main__":
    port=int(os.getenv("PORT","8000"))
    print(f"Perämeri-seuranta: http://localhost:{port}")
    ThreadingHTTPServer(("0.0.0.0",port),Handler).serve_forever()
