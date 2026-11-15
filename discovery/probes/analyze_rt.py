import sys, time, collections, statistics
from google.transit import gtfs_realtime_pb2 as pb
d = sys.argv[1]
now = time.time()
def load(n):
    m = pb.FeedMessage(); m.ParseFromString(open(f"{d}/{n}.pb","rb").read()); return m
for n in ["VehiclePositions","TripUpdates","Alerts"]:
    m = load(n)
    h = m.header
    print(f"\n=== {n} === version={h.gtfs_realtime_version} incrementality={h.incrementality} header_ts={h.timestamp} age_s={now-h.timestamp:.0f} entities={len(m.entity)}")
    if n=="VehiclePositions":
        c=collections.Counter(); ages=[]; fields=collections.Counter(); sched=collections.Counter(); routes=set(); lat=[];lon=[]
        for e in m.entity:
            v=e.vehicle
            fields.update(f.name for f,_ in v.ListFields())
            if v.HasField("position"):
                lat.append(v.position.latitude); lon.append(v.position.longitude)
            if v.timestamp: ages.append(h.timestamp-v.timestamp)
            if v.HasField("trip"):
                routes.add(v.trip.route_id); sched[v.trip.schedule_relationship]+=1
                fields.update("trip."+f.name for f,_ in v.trip.ListFields())
            if v.HasField("vehicle"): fields.update("vehicle."+f.name for f,_ in v.vehicle.ListFields())
            c[v.occupancy_status if v.HasField("occupancy_status") else -1]+=1
        print("field presence:",dict(fields))
        print("distinct route_ids:",len(routes)," schedule_relationship:",dict(sched)," occupancy:",dict(c))
        if ages: print("vehicle ts age vs header: min/median/max s = %d/%d/%d"%(min(ages),statistics.median(ages),max(ages)))
        print("lat range %.3f..%.3f lon range %.3f..%.3f"%(min(lat),max(lat),min(lon),max(lon)))
        print("sample:",str(m.entity[0]).replace("\n"," ")[:600])
    if n=="TripUpdates":
        fields=collections.Counter(); sched=collections.Counter(); delays=[]; withdelay=0; stu=0; stu_delay=0; stu_time_only=0; routes=set(); tu_delay_field=0
        nstu=[]
        for e in m.entity:
            t=e.trip_update
            fields.update(f.name for f,_ in t.ListFields())
            sched[t.trip.schedule_relationship]+=1; routes.add(t.trip.route_id)
            if t.HasField("delay"): tu_delay_field+=1
            nstu.append(len(t.stop_time_update))
            for s in t.stop_time_update:
                stu+=1
                for k in ("arrival","departure"):
                    if s.HasField(k):
                        ev=getattr(s,k)
                        if ev.HasField("delay"): stu_delay+=1; delays.append(ev.delay)
                        elif ev.HasField("time"): stu_time_only+=1
        print("trip_update field presence:",dict(fields))
        print("distinct route_ids:",len(routes)," trip schedule_relationship:",dict(sched))
        print("trip-level delay field present on",tu_delay_field,"of",len(m.entity))
        print("stop_time_updates:",stu," events with delay:",stu_delay," events with time only:",stu_time_only)
        if nstu: print("stop_time_updates per trip min/median/max:",min(nstu),statistics.median(nstu),max(nstu))
        if delays:
            ds=sorted(delays); print("delay s: min %d p10 %d median %d p90 %d max %d ; share>=300s %.1f%% ; share<0 %.1f%%"%(ds[0],ds[len(ds)//10],statistics.median(ds),ds[9*len(ds)//10],ds[-1],100*sum(x>=300 for x in ds)/len(ds),100*sum(x<0 for x in ds)/len(ds)))
        print("sample:",str(m.entity[0]).replace("\n"," ")[:700])
    if n=="Alerts":
        fields=collections.Counter(); causes=collections.Counter(); eff=collections.Counter(); noper=0; active=0; ent_kinds=collections.Counter(); langs=collections.Counter()
        for e in m.entity:
            a=e.alert
            fields.update(f.name for f,_ in a.ListFields())
            causes[a.cause]+=1; eff[a.effect]+=1
            if not a.active_period: noper+=1
            for p in a.active_period:
                s=p.start or 0; en=p.end or 1<<62
                if s<=now<=en: active+=1; break
            for i in a.informed_entity:
                ent_kinds.update(f.name for f,_ in i.ListFields())
            for tr in a.header_text.translation: langs[tr.language]+=1
        print("alert field presence:",dict(fields))
        print("cause:",dict(causes)," effect:",dict(eff))
        print("alerts with no active_period:",noper," alerts active now by period:",active)
        print("informed_entity kinds:",dict(ent_kinds)," header langs:",dict(langs))
        if m.entity: print("sample:",str(m.entity[0]).replace("\n"," ")[:800])
