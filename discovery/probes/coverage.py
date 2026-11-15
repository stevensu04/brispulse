import sys, csv, collections, datetime, statistics, subprocess
from google.transit import gtfs_realtime_pb2 as pb
S=sys.argv[1]; R=sys.argv[2]
def hms(s):
    h,m,sec=s.split(":"); return int(h)*3600+int(m)*60+int(sec)
tu=pb.FeedMessage(); tu.ParseFromString(open(f"{R}/TripUpdates.pb","rb").read())
vp=pb.FeedMessage(); vp.ParseFromString(open(f"{R}/VehiclePositions.pb","rb").read())
ts=tu.header.timestamp
tz=datetime.timezone(datetime.timedelta(hours=10))  # Brisbane has no DST
now=datetime.datetime.fromtimestamp(ts,tz); today=now.strftime("%Y%m%d"); dow=now.strftime("%A").lower()
secs=now.hour*3600+now.minute*60+now.second
print("snapshot local:",now.isoformat(),"service date",today)
with open(f"{S}/calendar.txt",newline="",encoding="utf-8-sig") as f:
    cal=list(csv.DictReader(f))
act={r["service_id"] for r in cal if r["start_date"]<=today<=r["end_date"] and r[dow]=="1"}
with open(f"{S}/calendar_dates.txt",newline="",encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        if r["date"]==today:
            (act.add if r["exception_type"]=="1" else act.discard)(r["service_id"])
trips={}
with open(f"{S}/trips.txt",newline="",encoding="utf-8-sig") as f:
    for r in csv.DictReader(f): trips[r["trip_id"]]=r
routes={}
with open(f"{S}/routes.txt",newline="",encoding="utf-8-sig") as f:
    for r in csv.DictReader(f): routes[r["route_id"]]=r
want={t for t,r in trips.items() if r["service_id"] in act}
print("active service_ids today:",len(act)," trips scheduled today:",len(want),"of",len(trips))
tu_trips={e.trip_update.trip.trip_id:e.trip_update for e in tu.entity}
sample={t for t in tu_trips if t in want}
span={}; sched={}
with open(f"{S}/stop_times.txt",newline="",encoding="utf-8-sig") as f:
    rd=csv.DictReader(f)
    for r in rd:
        t=r["trip_id"]
        if t not in want: continue
        a=hms(r["arrival_time"]) if r["arrival_time"] else None; d=hms(r["departure_time"]) if r["departure_time"] else None
        lo=a if a is not None else d; hi=d if d is not None else a
        if t in span: span[t]=(min(span[t][0],lo),max(span[t][1],hi))
        else: span[t]=(lo,hi)
        if t in sample: sched[(t,r["stop_id"],int(r["stop_sequence"]))]=(a,d)
inprog={t for t,(lo,hi) in span.items() if lo<=secs<=hi}
mode=lambda t: routes[trips[t]["route_id"]]["route_type"]
print(f"scheduled trips in progress at snapshot: {len(inprog)}")
vp_trips={e.vehicle.trip.trip_id for e in vp.entity}; tu_ids=set(tu_trips)
print(f"  of those: with a TripUpdate {len(inprog&tu_ids)} ({100*len(inprog&tu_ids)/len(inprog):.1f}%), with a VehiclePosition {len(inprog&vp_trips)} ({100*len(inprog&vp_trips)/len(inprog):.1f}%)")
for m,n in (("3","bus"),("2","rail"),("4","ferry"),("0","tram")):
    ip={t for t in inprog if mode(t)==m}
    print(f"  {n}: in-progress {len(ip)}, with TU {len(ip&tu_ids)}, with VP {len(ip&vp_trips)}")
print(f"TU trips not scheduled today per static: {len(tu_ids-want)} ; VP trips not scheduled today: {len(vp_trips-want)}")
# TU trips outside scheduled in-progress window
print(f"TU trips whose scheduled span does not include 'now': {len(tu_ids&want-inprog)} (TU also covers future/just-finished trips)")
# consistency: predicted time - delay == scheduled (seconds since midnight local)
midnight=datetime.datetime(now.year,now.month,now.day,tzinfo=tz).timestamp()
diffs=[]; miss=0
for t,u in tu_trips.items():
    if t not in want: continue
    for s in u.stop_time_update:
        for k in ("arrival","departure"):
            if s.HasField(k):
                ev=getattr(s,k)
                if ev.HasField("time") and ev.HasField("delay"):
                    sch=sched.get((t,s.stop_id,s.stop_sequence))
                    if not sch: miss+=1; continue
                    sv=sch[0] if k=="arrival" else sch[1]
                    if sv is None: miss+=1; continue
                    diffs.append((ev.time-ev.delay-midnight)-sv)
c=collections.Counter(int(d) for d in diffs)
print(f"\nconsistency (time - delay) - scheduled_secs: n={len(diffs)} unmatched={miss}; exact==0: {100*c[0]/len(diffs):.1f}% ; within ±60s: {100*sum(v for k,v in c.items() if abs(k)<=60)/len(diffs):.1f}%; most common offsets: {c.most_common(5)}")
