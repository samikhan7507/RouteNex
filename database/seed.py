"""Deterministic, idempotent Jaipur operations dataset. Use --reset to rebuild all demo data."""
import sqlite3, pathlib, sys, random, json, datetime, os, secrets
sys.path.insert(0,str(pathlib.Path(__file__).parents[1]/'backend'))
from security import hash_password
from config import DB_PATH            # same database file the app uses (honours ROUTENEX_DB and backend/.env)
root=pathlib.Path(__file__).parent; db=DB_PATH; random.seed(42)
ADMIN_EMAIL=(os.getenv('ADMIN_EMAIL') or 'samikhan@routenex.in').strip().lower(); ADMIN_NAME=(os.getenv('ADMIN_NAME') or 'Sami Khan').strip()
c=sqlite3.connect(db); c.execute('PRAGMA foreign_keys=ON'); c.executescript((root/'schema.sql').read_text())
if '--reset' in sys.argv:
    c.execute('PRAGMA foreign_keys=OFF')
    for t in ['route_orders','order_items','maintenance','notifications','audit_logs','alerts','routes','rides','orders','addresses','drivers','vehicles','items','otp_codes','users']: c.execute(f'DELETE FROM {t}')
    c.execute('PRAGMA foreign_keys=ON')
roles=[
('Aarav Sharma','customer@routenex.in','8882846897','customer'),('Diya Rathore','driver@routenex.in','9000000002','driver'),('Kabir Mehta','dispatcher@routenex.in','9000000003','dispatcher'),('Meera Joshi','fleet@routenex.in','9000000004','fleet_manager'),(ADMIN_NAME,ADMIN_EMAIL,'9000000005','admin'),
('Rohan Gupta','rohan@routenex.in','9000000011','customer'),('Ishita Jain','ishita@routenex.in','9000000012','customer'),('Vivaan Saini','vivaan@routenex.in','9000000013','customer'),('Saanvi Verma','saanvi@routenex.in','9000000014','customer'),('Arjun Yadav','arjun@routenex.in','9000000015','customer'),('Myra Khan','myra@routenex.in','9000000016','customer'),('Advait Pareek','advait@routenex.in','9000000017','customer'),('Kiara Bansal','kiara@routenex.in','9000000018','customer'),
('Mohit Gurjar','driver2@routenex.in','9000000022','driver'),('Neha Kumari','driver3@routenex.in','9000000023','driver'),('Farhan Ali','driver4@routenex.in','9000000024','driver'),('Pooja Choudhary','driver5@routenex.in','9000000025','driver'),('Rahul Solanki','driver6@routenex.in','9000000026','driver'),('Nitin Sharma','driver7@routenex.in','9000000027','driver'),('Salma Qureshi','driver8@routenex.in','9000000028','driver'),('Devendra Singh','driver9@routenex.in','9000000029','driver'),('Kavita Meena','driver10@routenex.in','9000000030','driver'),('Imran Sheikh','driver11@routenex.in','9000000031','driver'),('Sunita Yadav','driver12@routenex.in','9000000032','driver'),
('Lakshya Operations','dispatcher2@routenex.in','9000000041','dispatcher'),('Naina Fleet','fleet2@routenex.in','9000000042','fleet_manager')]
demo_hash=hash_password('Demo@123'); admin_hash=hash_password(os.getenv('ADMIN_PASSWORD') or secrets.token_urlsafe(18))   # the admin is never given the public demo password
for n,e,p,r in roles:c.execute('INSERT OR IGNORE INTO users(name,email,phone,password_hash,role) VALUES(?,?,?,?,?)',(n,e,p,admin_hash if r=='admin' else demo_hash,r))
from services.catalog import seed_rows      # the real-world student catalogue (backend/services/catalog.py)
items=seed_rows()
if c.execute('SELECT COUNT(*) FROM items').fetchone()[0]==0:
    c.executemany('INSERT INTO items(name,description,category,price,stock,icon) VALUES(?,?,?,?,?,?)',items)
locations=[('C-Scheme',26.9124,75.7873,'302001'),('Malviya Nagar',26.8540,75.8243,'302017'),('Vaishali Nagar',26.9126,75.7442,'302021'),('Mansarovar',26.8505,75.7628,'302020'),('Jagatpura',26.8399,75.8322,'302017'),('Raja Park',26.8942,75.8210,'302004'),('Bani Park',26.9322,75.7933,'302016'),('Tonk Road',26.8735,75.7950,'302018'),('Amer',26.9855,75.8513,'302028'),('Sitapura',26.7751,75.8514,'302022'),('Jhotwara',26.9540,75.7420,'302012'),('Civil Lines',26.9064,75.7790,'302006')]
customers=c.execute("SELECT id FROM users WHERE role='customer' ORDER BY id").fetchall()
for i,(uid,) in enumerate(customers):
    name,lat,lng,pin=locations[i%len(locations)]; c.execute('INSERT OR IGNORE INTO addresses(id,user_id,label,line1,city,state,pincode,lat,lng) VALUES(?,?,?,?,?,?,?,?,?)',(i+1,uid,'Home',f'{12+i}, {name} Main Road','Jaipur','Rajasthan',pin,lat,lng))
vehicles=[('RJ14-RN-101','Bike',20,4),('RJ14-RN-102','Bike',25,4.2),('RJ14-RN-201','Electric Cargo',350,7),('RJ14-RN-202','Mini Van',650,12),('RJ14-RN-203','Van',900,14),('RJ14-RN-301','Pickup',1200,17),('RJ14-RN-302','Pickup',1500,18),('RJ14-RN-401','Reefer Van',800,20),('RJ14-RN-501','Truck',3500,26),('RJ14-RN-502','Truck',5000,31),('RJ14-RN-601','EV Van',700,8),('RJ14-RN-701','Tow Vehicle',1800,22)]
for i,(plate,typ,cap,cost) in enumerate(vehicles):
    loc=locations[(i+2)%len(locations)]; status='maintenance' if i==9 else ('assigned' if i in (2,3,5) else 'available')
    c.execute('INSERT OR IGNORE INTO vehicles(plate,type,capacity_kg,available,status,lat,lng,documents,next_maintenance,cost_per_km) VALUES(?,?,?,?,?,?,?,?,?,?)',(plate,typ,cap,1 if status=='available' else 0,status,loc[1],loc[2],'RC✓ Insurance✓ PUC✓',f'2026-{11+(i%2):02d}-{5+(i%20):02d}',cost))
driver_users=c.execute("SELECT id FROM users WHERE role='driver' ORDER BY id").fetchall(); vehicle_rows=c.execute('SELECT id,status,lat,lng FROM vehicles ORDER BY id').fetchall()
for i,(uid,) in enumerate(driver_users[:12]):
    vid,vstatus,lat,lng=vehicle_rows[i]; available=1 if vstatus=='available' else 0
    c.execute('INSERT OR IGNORE INTO drivers(user_id,license,capacity_rating,available,status,lat,lng,documents,vehicle_id) VALUES(?,?,?,?,?,?,?,?,?)',(uid,f'RJ14-202{i}-00{i+11:02d}',round(4.2+(i%8)*.1,1),available,'available' if available else vstatus,lat+.002,lng-.002,'License✓ Police✓ Medical✓',vid))
# Build 38 orders spanning 14 days, including enough pending work for optimizer.
if c.execute('SELECT COUNT(*) FROM orders').fetchone()[0]<30:
    c.execute('DELETE FROM route_orders');c.execute('DELETE FROM order_items');c.execute('DELETE FROM routes');c.execute('DELETE FROM orders')
    now=datetime.datetime.now(); order_ids=[]
    statuses=['delivered']*20+['in_transit']*4+['placed']*10+['cancelled']*2+['pending']*2
    for i,status in enumerate(statuses):
        uid=customers[i%len(customers)][0]; aid=(i%len(customers))+1; loc=locations[i%len(locations)]; created=now-datetime.timedelta(days=(37-i)//3,hours=i%8)
        item=(i*7)%len(items)+1; qty=1+i%3; total=round(items[item-1][3]*qty,2); priority=1+(i%5)
        oid=c.execute('INSERT INTO orders(user_id,address_id,status,priority,delivery_window,total,lat,lng,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)',(uid,aid,status,priority,f'{9+i%9:02d}:00–{11+i%9:02d}:00',total,loc[1],loc[2],created.isoformat(' '),(created+datetime.timedelta(minutes=35+i%70)).isoformat(' '))).lastrowid;order_ids.append(oid)
        c.execute('INSERT INTO order_items(order_id,item_id,quantity,unit_price) VALUES(?,?,?,?)',(oid,item,qty,items[item-1][3]))
    # Historical routes attached to delivered/in-transit orders.
    for r in range(8):
        v=vehicle_rows[r][0]; did=c.execute('SELECT id FROM drivers WHERE vehicle_id=?',(v,)).fetchone()[0]; pts=[[locations[(r+j)%12][1],locations[(r+j)%12][2]] for j in range(4)]
        rid=c.execute('INSERT INTO routes(vehicle_id,driver_id,status,distance_km,duration_min,cost,geometry,reason,created_at) VALUES(?,?,?,?,?,?,?,?,?)',(v,did,'completed' if r<6 else 'active',round(16+r*3.7,1),58+r*9,round((16+r*3.7)*vehicles[r][3],2),json.dumps(pts),'capacity + priority + delivery windows + Jaipur traffic',(now-datetime.timedelta(days=7-r)).isoformat(' '))).lastrowid
        for seq,oid in enumerate(order_ids[r*3:r*3+3],1): c.execute('INSERT OR IGNORE INTO route_orders(route_id,order_id,stop_sequence,eta) VALUES(?,?,?,?)',(rid,oid,seq,f'{15+seq*12} min'));c.execute('UPDATE orders SET route_id=? WHERE id=?',(rid,oid))
# Ride history.
if c.execute('SELECT COUNT(*) FROM rides').fetchone()[0]<10:
    c.execute('DELETE FROM rides'); driver_ids=[x[0] for x in c.execute('SELECT id FROM drivers').fetchall()]; now=datetime.datetime.now()
    for i in range(18):
        a=locations[i%12];b=locations[(i+3)%12];km=round(((a[1]-b[1])**2+(a[2]-b[2])**2)**.5*105,1);status=['completed']*13+['started','arriving','matched','cancelled','completed'][i%5] if False else ('completed' if i<13 else ['started','arriving','matched','cancelled','completed'][i-13])
        c.execute('INSERT INTO rides(user_id,driver_id,pickup,pickup_lat,pickup_lng,dropoff,drop_lat,drop_lng,distance_km,fare,eta_min,status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(customers[i%len(customers)][0],driver_ids[i%len(driver_ids)],a[0],a[1],a[2],b[0],b[1],b[2],km,round(45+km*12.5,2),max(5,round(km*2.7)),status,(now-datetime.timedelta(days=17-i)).isoformat(' ')))
if c.execute('SELECT COUNT(*) FROM alerts').fetchone()[0]<5:
    c.execute('DELETE FROM alerts'); alerts=[('traffic','medium','Heavy congestion on Tonk Road; ETA adjusted','route',7,0),('delay','high','Priority order #28 is 18 minutes behind window','order',28,0),('maintenance','low','RJ14-RN-502 service due in 7 days','vehicle',10,0),('capacity','medium','Sitapura demand approaching van capacity','zone',4,1),('weather','low','Light rain forecast; bike ETAs increased 8%','network',1,0),('document','high','Insurance renewal review required','vehicle',7,0)]
    c.executemany('INSERT INTO alerts(type,severity,message,entity_type,entity_id,acknowledged) VALUES(?,?,?,?,?,?)',alerts)
for vid in [5,10]:c.execute('INSERT OR IGNORE INTO maintenance(id,vehicle_id,description,scheduled_for,status,cost) VALUES(?,?,?,?,?,?)',(vid,vid,'Preventive service and brake inspection',f'2026-11-{10+vid:02d}','scheduled',4200+vid*100))
admin=c.execute("SELECT id FROM users WHERE role='admin' LIMIT 1").fetchone()[0]
if c.execute('SELECT COUNT(*) FROM audit_logs').fetchone()[0]<10:
    for i in range(15):c.execute('INSERT INTO audit_logs(user_id,action,entity,entity_id,details) VALUES(?,?,?,?,?)',(admin,['LOGIN','OPTIMIZE','STATUS','ASSIGN'][i%4],['user','route','order','driver'][i%4],str(i+1),'Seeded operational audit event'))
c.commit()
print(f'Seeded {db}:',dict(users=c.execute('SELECT COUNT(*) FROM users').fetchone()[0],orders=c.execute('SELECT COUNT(*) FROM orders').fetchone()[0],vehicles=c.execute('SELECT COUNT(*) FROM vehicles').fetchone()[0],drivers=c.execute('SELECT COUNT(*) FROM drivers').fetchone()[0],rides=c.execute('SELECT COUNT(*) FROM rides').fetchone()[0],routes=c.execute('SELECT COUNT(*) FROM routes').fetchone()[0]))
