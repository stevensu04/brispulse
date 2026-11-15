import sys, csv, collections, datetime, statistics
from google.transit import gtfs_realtime_pb2 as pb
S=sys.argv[1]
routes={r["route_id"]:r for r in csv.DictReader(open(f"{S}/routes.txt",encoding="utf-8-sig"))}
MODE={"0":"tram","2":"rail","3":"bus","4":"ferry"}
def hms(s):
    h,m,x=s.split(":"); return int(h)*3600+int(m)*60+int(x)
for R in sys.argv[2:]:
    vp=pb.FeedMessage(); vp.ParseFromString(open(f"{R}/VehiclePositions.pb","rb").read())
    tu=pb.FeedMessage(); tu.ParseFromString(open(f"{R}/TripUpdates.pb","rb").read())
    tz=datetime.timezone(datetime.timedelta(hours=10)); now=datetime.datetime.fromtimestamp(tu.header.timestamp,tz)
    secs=now.hour*3600+now.minute*60+now.second; today=now.strftime("%Y%m%d")
    vpt={e.vehicle.trip.trip_id:e.vehicle for e in vp.entity}
    pm=collections.defaultdict(list); allv=[]
    for e in tu.entity:
        t=e.trip_update; v=vpt.get(t.trip.trip_id)
        if v is None or vp.header.timestamp-v.timestamp>90: continue
        if not (t.trip.start_date==today and hms(t.trip.start_time)<=secs): continue
        if t.trip.schedule_relationship==3: continue
        d=None
        for s in t.stop_time_update:
            ev=s.arrival if s.HasField("arrival") else (s.departure if s.HasField("departure") else None)
            if ev is not None and ev.HasField("delay"): d=ev.delay; break
        if d is None: continue
        pm[MODE[routes[t.trip.route_id]["route_type"]]].append(d); allv.append(d)
    print(f"\n{now:%H:%M:%S} running trips (started, fresh vehicle<=90s, has delay): {len(allv)} of {len(tu.entity)} trip updates")
    for k,v in list(pm.items())+[("ALL",allv)]:
        v=sorted(v); n=len(v)
        print(f"  {k:5s} n={n:4d} median={statistics.median(v):5.0f}s p90={v[9*n//10]:5d}s  on-time[-60,300]={100*sum(-60<=x<=300 for x in v)/n:4.1f}% late>300={100*sum(x>300 for x in v)/n:4.1f}% early<-60={100*sum(x<-60 for x in v)/n:4.1f}%  |d|>1800: {sum(abs(x)>1800 for x in v)}  min={v[0]} max={v[-1]}")
