import sys, csv, collections, datetime, statistics, time, resource
from google.transit import gtfs_realtime_pb2 as pb
S=sys.argv[1]; R=sys.argv[2]
def load(n):
    b=open(f"{R}/{n}.pb","rb").read(); t=time.perf_counter(); m=pb.FeedMessage(); m.ParseFromString(b)
    return m, len(b), time.perf_counter()-t
vp,vb,vt=load("VehiclePositions"); tu,tb,tt=load("TripUpdates"); al,ab,at=load("Alerts")
print(f"decode: VP {vb}B {vt*1000:.0f}ms | TU {tb}B {tt*1000:.0f}ms | Alerts {ab}B {at*1000:.0f}ms | maxRSS {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1e6:.0f}MB(mac bytes)")
hts=tu.header.timestamp; tz=datetime.timezone(datetime.timedelta(hours=10)); now=datetime.datetime.fromtimestamp(hts,tz)
secs=now.hour*3600+now.minute*60+now.second; today=now.strftime("%Y%m%d")
print("snapshot",now.isoformat(),"entities VP/TU/AL",len(vp.entity),len(tu.entity),len(al.entity))
routes={r["route_id"]:r for r in csv.DictReader(open(f"{S}/routes.txt",encoding="utf-8-sig"))}
MODE={"0":"tram","2":"rail","3":"bus","4":"ferry"}
vpt={e.vehicle.trip.trip_id:e.vehicle for e in vp.entity}
ages=[vp.header.timestamp-e.vehicle.timestamp for e in vp.entity]
print("VP stale share >90s %.1f%% >300s %.1f%% >900s %.1f%% max %ds"%(100*sum(a>90 for a in ages)/len(ages),100*sum(a>300 for a in ages)/len(ages),100*sum(a>900 for a in ages)/len(ages),max(ages)))
def hms(s):
    h,m,x=s.split(":"); return int(h)*3600+int(m)*60+int(x)
def first_delay(t):
    for s in t.stop_time_update:
        ev=s.arrival if s.HasField("arrival") else (s.departure if s.HasField("departure") else None)
        if ev is not None and ev.HasField("delay"): return ev.delay, s.stop_sequence
    return None,None
# H4: future-trip hypothesis
groups=collections.defaultdict(list); sd=collections.Counter()
seqgap=collections.Counter(); firstseq_is_1=0; n_running=0
for e in tu.entity:
    t=e.trip_update; sd[t.trip.start_date]+=1
    d,seq=first_delay(t)
    if d is None: groups["no_delay"].append(0); continue
    started = (t.trip.start_date<today) or (t.trip.start_date==today and hms(t.trip.start_time)<=secs)
    has_vp = t.trip.trip_id in vpt
    fresh = has_vp and (vp.header.timestamp-vpt[t.trip.trip_id].timestamp)<=90
    key=("started" if started else "not_started")+("+freshVP" if fresh else ("+staleVP" if has_vp else "+noVP"))
    groups[key].append(d)
    if has_vp:
        n_running+=1; v=vpt[t.trip.trip_id]
        if v.HasField("current_stop_sequence"):
            g=seq-v.current_stop_sequence; seqgap[max(-3,min(3,g))]+=1
print("\nH4 next-stop delay by trip state: (n, share==0, median, p90, min, max)")
for k,v in sorted(groups.items()):
    v2=sorted(v); print(f"  {k:24s} n={len(v):5d} zero={100*sum(x==0 for x in v)/len(v):5.1f}% median={statistics.median(v2):6.0f} p90={v2[9*len(v2)//10]:6d} min={v2[0]:6d} max={v2[-1]:6d}")
print("TU start_date distribution:",dict(sd))
print("first STU stop_sequence minus VP current_stop_sequence (clamped ±3):",dict(sorted(seqgap.items())),"of",n_running)
# Trips with VP but not in TU, TU without vehicle descriptor
tuid={e.trip_update.trip.trip_id for e in tu.entity}
print("VP trips not in TU:",len(set(vpt)-tuid)," TU without vehicle field:",sum(1 for e in tu.entity if not e.trip_update.HasField("vehicle")))
# REPLACEMENT semantics
rep=[e.trip_update for e in tu.entity if e.trip_update.trip.schedule_relationship==5]
rm=collections.Counter(MODE.get(routes.get(t.trip.route_id,{}).get("route_type"),"?") for t in rep)
rr=collections.Counter(t.trip.route_id for t in rep)
print(f"\nREPLACEMENT trips: {len(rep)} by mode {dict(rm)}; top routes {rr.most_common(6)}; with VP {sum(t.trip.trip_id in vpt for t in rep)}")
if rep:
    t=rep[0]; print("  sample:",t.trip.trip_id,t.trip.route_id,routes.get(t.trip.route_id,{}).get("route_long_name"),"stus",len(t.stop_time_update),"first delay",first_delay(t))
    skipped=sum(1 for t in rep for s in t.stop_time_update if s.schedule_relationship==1)
    print("  SKIPPED stops inside REPLACEMENT trips:",skipped,"; stop-level relationships overall:",dict(collections.Counter(s.schedule_relationship for e in tu.entity for s in e.trip_update.stop_time_update)))
print("trip-level relationships:",dict(collections.Counter(e.trip_update.trip.schedule_relationship for e in tu.entity)))
# delay metric on the proposed population: started + fresh VP, per mode
pm=collections.defaultdict(list)
for e in tu.entity:
    t=e.trip_update
    if t.trip.trip_id in vpt and (vp.header.timestamp-vpt[t.trip.trip_id].timestamp)<=90:
        d,_=first_delay(t)
        if d is not None: pm[MODE.get(routes[t.trip.route_id]["route_type"],"?")].append(d)
print("\nproposed population (fresh vehicle + trip update), next-stop delay by mode:")
for k,v in pm.items():
    v.sort(); n=len(v); print(f"  {k:5s} n={n:4d} median={statistics.median(v):5.0f}s p90={v[9*n//10]:5d}s late>300s={100*sum(x>300 for x in v)/n:4.1f}% early<-60s={100*sum(x<-60 for x in v)/n:4.1f}% |d|>3600: {sum(abs(x)>3600 for x in v)}")
# routes with few vehicles
rc=collections.Counter(e.vehicle.trip.route_id for e in vp.entity)
sizes=sorted(rc.values()); print("vehicles per route: routes",len(sizes),"median",statistics.median(sizes),"routes with <3 vehicles",sum(s<3 for s in sizes),"max",sizes[-1])
# alerts
act=sum(1 for e in al.entity if any((p.start or 0)<=hts<=(p.end or 1<<62) for p in e.alert.active_period))
print("alerts",len(al.entity),"active now",act)
