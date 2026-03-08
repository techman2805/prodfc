import requests
import time
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

# ======================
# CONFIG
# ======================

WEBHOOK_URL = "https://discord.com/api/webhooks/1479454664809386088/STcConwFImwGLctUM0Yg_jOuzn_POphiPeWv_5xTyydxS3P6ZVziws_KknNX3D41ftuW"

CHECK_INTERVAL = 8
MAX_THREADS = 6
DATA_FILE = "database.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
    "Referer": "https://www.firstcry.com/",
    "Origin": "https://www.firstcry.com",
    "X-Requested-With": "XMLHttpRequest"
}

# ======================
# APIS
# ======================

APIS = [
{
"name":"1335 New Arrivals",
"url":"https://www.firstcry.com/svcs/SearchResult.svc/GetSearchResultProductsPaging",
"params":{
"PageNo":1,
"PageSize":20,
"SortExpression":"NewArrivals",
"OnSale":0,
"SearchString":"brand",
"MasterBrand":1335,
"pcode":600119,
"isclub":1
}
},
{
"name":"1335 Popular",
"url":"https://www.firstcry.com/svcs/SearchResult.svc/GetSearchResultProductsPaging",
"params":{
"PageNo":1,
"PageSize":20,
"SortExpression":"popularity",
"OnSale":5,
"SearchString":"brand",
"MasterBrand":1335,
"pcode":600119,
"isclub":1
}
}
]

# ======================
# SESSION
# ======================

session = requests.Session()
session.headers.update(HEADERS)
session.get("https://www.firstcry.com/")

# ======================
# LOGGER
# ======================

def log(level,msg):
    now=datetime.now().strftime("%H:%M:%S")
    print(f"[{level}] {now} | {msg}")

# ======================
# DATABASE
# ======================

def load_db():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE) as f:
            return json.load(f)
    return {}

def save_db(data):
    with open(DATA_FILE,"w") as f:
        json.dump(data,f,indent=2)

# ======================
# UTILITIES
# ======================

def slugify(text):
    text=text.lower()
    text=re.sub(r'[^a-z0-9]+','-',text)
    return text.strip('-')

# ======================
# DISCORD ALERT
# ======================

def send_discord(product,title,color,previous=None,analytics=None):

    timestamp=datetime.now().strftime("%H:%M:%S")

    qty_text=f"**Only {product['qty']} Left!**" if product["qty"]>0 else "0"

    fields=[
        {"name":"🏷 Product","value":product["name"],"inline":False},
        {"name":"💰 Price","value":f"₹{product['price']}","inline":True},
        {"name":"📦 Status","value":product["stock"],"inline":True},
        {"name":"🔢 Quantity","value":qty_text,"inline":True}
    ]

    if previous:
        fields.append({"name":"🕒 Previous","value":previous,"inline":False})

    if analytics:
        fields.append({"name":"📊 Analytics","value":analytics,"inline":False})

    embed={
        "title":"Hot Wheels Stock Bot",
        "description":f"{title}\n\n👉 **[Click here to Buy on FirstCry]({product['url']})**",
        "color":color,
        "thumbnail":{"url":product["image"]},
        "fields":fields,
        "footer":{"text":f"FirstCry Monitor • {timestamp}"}
    }

    payload={"embeds":[embed]}

    try:
        requests.post(WEBHOOK_URL,json=payload,timeout=10)
    except:
        pass

# ======================
# FETCH PAGE
# ======================

def fetch_page(api,page):

    params=api["params"].copy()
    params["PageNo"]=page

    try:
        r=session.get(api["url"],params=params,timeout=15)
        data=r.json()
    except:
        return []

    response=data.get("ProductResponse")

    if not response:
        return []

    parsed=json.loads(response)
    products=parsed.get("Products",[])

    log("DEBUG",f"{api['name']} P{page} → {len(products)} items")

    return products

# ======================
# PARSE PRODUCT
# ======================

def parse_product(p):

    pid=str(p.get("PId"))

    name=p.get("PNm","")
    brand=p.get("BNm","")

    qty=p.get("CrntStock")

    try:
        qty=int(qty)
    except:
        qty=0

    brand_slug=slugify(brand)
    product_slug=slugify(name)

    url=f"https://www.firstcry.com/{brand_slug}/{product_slug}/{pid}/product-detail"

    image=f"https://cdn.fcglcdn.com/brainbees/images/products/438x531/{pid}a.webp"

    return{
        "id":pid,
        "name":name,
        "price":p.get("SP",p.get("MRP")),
        "old_price":p.get("MRP"),
        "qty":qty,
        "stock":"🟢 **IN STOCK**" if qty>0 else "🔴 **OUT OF STOCK**",
        "image":image,
        "url":url
    }

# ======================
# SCAN PRODUCTS
# ======================

def scan_products():

    start=time.time()

    log("INFO","Scan Starting")

    products=[]

    with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:

        futures=[]

        for api in APIS:
            for page in range(1,8):
                futures.append(executor.submit(fetch_page,api,page))

        log("PERF",f"{len(futures)} pages → parallel fetch")

        for f in futures:
            result=f.result()
            if result:
                products.extend(result)

    elapsed=time.time()-start
    log("PERF",f"Fetched pages in {round(elapsed,2)}s")

    return products

# ======================
# MONITOR
# ======================

def monitor():

    db=load_db()

    log("OK","Hot Wheels Monitor Started")

    while True:

        alerts=0
        start=time.time()

        try:

            products=scan_products()

            log("INFO",f"Tracked: {len(products)} items")

            seen=set()

            for p in products:

                pid=str(p.get("PId"))

                if pid in seen:
                    continue

                seen.add(pid)

                product=parse_product(p)
                now=time.time()

                # NEW PRODUCT
                if pid not in db:

                    product["stock_start"]=now
                    product["status_changes"]=0
                    db[pid]=product

                    if product["qty"]>0:
                        send_discord(
                            product,
                            "🆕 **New Product In Stock!**",
                            3447003,
                            None,
                            "• New product detected"
                        )
                        alerts+=1

                    continue

                old=db[pid]

                analytics=f"• Status Changes: {old.get('status_changes',0)}"

                # PRICE DROP
                if product["price"] < old["price"]:
                    send_discord(product,"📉 **Price Drop Alert!**",3066993,f"₹{old['price']}",analytics)
                    alerts+=1

                # PRICE INCREASE
                if product["price"] > old["price"]:
                    send_discord(product,"📈 **Price Increase Alert!**",15105570,f"₹{old['price']}",analytics)
                    alerts+=1

                # OUT OF STOCK
                if old["qty"]>0 and product["qty"]==0:

                    duration=int((now-old.get("stock_start",now))/60)

                    analytics=f"• Stock Duration: {duration}m\n• Status Changes: {old.get('status_changes',0)+1}"

                    send_discord(product,"🔴 **Stock Alert: Out of Stock**",15158332,"IN_STOCK",analytics)

                    product["status_changes"]=old.get("status_changes",0)+1
                    alerts+=1

                # BACK IN STOCK
                if old["qty"]==0 and product["qty"]>0:

                    product["stock_start"]=now

                    analytics=f"• Status Changes: {old.get('status_changes',0)+1}"

                    send_discord(product,"🎉 **Back in Stock!**",5763719,"OUT_OF_STOCK",analytics)

                    product["status_changes"]=old.get("status_changes",0)+1
                    alerts+=1

                db[pid]=product

            save_db(db)

        except Exception as e:
            log("ERROR",f"Monitor error: {e}")

        elapsed=time.time()-start

        log("OK",f"Done in {round(elapsed,2)}s | {len(products)} items | {alerts} alerts")

        time.sleep(CHECK_INTERVAL)

# ======================
# START
# ======================

if __name__=="__main__":
    monitor()
