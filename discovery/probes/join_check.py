import sys, csv, collections, time, statistics
from google.transit import gtfs_realtime_pb2 as pb
S=sys.argv[1]; R=sys.argv[2]
def rd(n):
    with open(f"{S}/{n}",newline="",encoding="utf-8-sig") as f: return list(csv.DictReader(f))
routes={r["route_id"]:r for r in rd("routes.txt")}
types=collections.Counter(r["route_type"] for r in routes.values())
print("routes.txt route_type counts:",dict(types))
trips={}
with open(f"{S}/trips.txt",newline="",encoding="utf-8-sig") as f:
    for r in csv.DictReader(f): trips[r["trip_id"]]=r
stops={r["stop_id"]:r for r in rd("stops.txt")}
print("trips",len(trips),"stops",len(stops),"location_type:",dict(collections.Counter(s["location_type"] for s in stops.values())))
def load(n):
    m=pb.FeedMessage(); m.ParseFromString(open(f"{R}/{n}.pb","rb").read()); return m
vp=load("VehiclePositions"); tu=load("TripUpdates"); al=load("Alerts")
hts=vp.header.timestamp
# Vehicle join
ok_route=ok_trip=ok_stop=0; modes=collections.Counter(); ages=[]
for e in vp.entity:
    v=e.vehicle
    if v.trip.route_id in routes: ok_route+=1; modes[routes[v.trip.route_id]["route_type"]]+=1
    if v.trip.trip_id in trips: ok_trip+=1
    if v.stop_id in stops: ok_stop+=1
    ages.append(hts-v.timestamp)
n=len(vp.entity)
print(f"\nVP join: route_id in routes.txt {ok_route}/{n}; trip_id in trips.txt {ok_trip}/{n}; stop_id in stops.txt {ok_stop}/{n}")
print("VP vehicles by static route_type:",dict(modes))
for th in (60,120,300,600,1800):
    print(f"  VP age > {th}s: {sum(a>th for a in ages)} ({100*sum(a>th for a in ages)/n:.1f}%)")
# TU join
ok_route=ok_trip=0; modes=collections.Counter(); stop_ok=stop_all=0
for e in tu.entity:
    t=e.trip_update
    if t.trip.route_id in routes: ok_route+=1; modes[routes[t.trip.route_id]["route_type"]]+=1
    if t.trip.trip_id in trips: ok_trip+=1
    for s in t.stop_time_update:
        stop_all+=1; stop_ok+= s.stop_id in stops
n=len(tu.entity)
print(f"\nTU join: route_id {ok_route}/{n}; trip_id {ok_trip}/{n}; stop_id {stop_ok}/{stop_all}")
print("TU trips by route_type:",dict(modes))
# trips present in both VP and TU
vt={e.vehicle.trip.trip_id for e in vp.entity}; tt={e.trip_update.trip.trip_id for e in tu.entity}
print(f"trips in VP {len(vt)}, in TU {len(tt)}, in both {len(vt&tt)}")
# TU timestamps
tage=[hts-e.trip_update.timestamp for e in tu.entity if e.trip_update.timestamp]
print("TU entity ts age s min/median/max:",min(tage),statistics.median(tage),max(tage))
# delay per mode (first stop_time_update with delay of each trip)
bymode=collections.defaultdict(list)
for e in tu.entity:
    t=e.trip_update
    if t.trip.schedule_relationship!=0: continue
    d=None
    for s in t.stop_time_update:
        ev=s.arrival if s.HasField("arrival") else (s.departure if s.HasField("departure") else None)
        if ev is not None and ev.HasField("delay"): d=ev.delay; break
    if d is not None and t.trip.route_id in routes: bymode[routes[t.trip.route_id]["route_type"]].append(d)
print("\nnext-stop predicted delay per trip, by route_type (n, median, p90, max):")
for k,v in sorted(bymode.items()):
    v.sort(); print(" ",k,len(v),statistics.median(v),v[9*len(v)//10],v[-1])
# alerts join
rids=set(); sids=set(); bad_r=bad_s=0
for e in al.entity:
    for i in e.alert.informed_entity:
        if i.route_id:
            rids.add(i.route_id); bad_r+= i.route_id not in routes
        if i.stop_id:
            sids.add(i.stop_id); bad_s+= i.stop_id not in stops
print(f"\nAlerts: distinct route_ids {len(rids)} (not in routes.txt: {len([r for r in rids if r not in routes])}); distinct stop_ids {len(sids)} (not in stops.txt: {len([s for s in sids if s not in stops])})")
# enum names
print("\nenum names: TripDescriptor.ScheduleRelationship",{n:v for n,v in pb.TripDescriptor.ScheduleRelationship.items()})
print("Alert.Cause",{v:n for n,v in pb.Alert.Cause.items()}); print("Alert.Effect",{v:n for n,v in pb.Alert.Effect.items()})
