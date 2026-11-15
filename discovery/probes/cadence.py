import time, subprocess, collections
from google.transit import gtfs_realtime_pb2 as pb
base="https://gtfsrt.api.translink.com.au/api/realtime/SEQ/"
last={}; changes=collections.defaultdict(list); t0=time.time()
while time.time()-t0<75:
    for n in ("VehiclePositions","TripUpdates","Alerts"):
        b=subprocess.run(["curl","-sS","-m","30",base+n],capture_output=True,check=True).stdout
        m=pb.FeedMessage(); m.ParseFromString(b); h=m.header.timestamp
        if last.get(n)!=h:
            changes[n].append((round(time.time()-t0),h,len(m.entity))); last[n]=h
    time.sleep(4)
for n,c in changes.items():
    ts=[x[1] for x in c]; gaps=[b-a for a,b in zip(ts,ts[1:])]
    print(n,"distinct header timestamps in 75s:",len(c),"gaps(s):",gaps)
