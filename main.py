import requests
import time
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor

# ======================
# CONFIG
# ======================

WEBHOOK_URL = "https://discord.com/api/webhooks/1479454664809386088/STcConwFImwGLctUM0Yg_jOuzn_POphiPeWv_5xTyydxS3P6ZVziws_KknNX3D41ftuW"

CHECK_INTERVAL = 8
MAX_THREADS = 5
DATA_FILE = "database.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
    "Referer": "https://www.firstcry.com/",
    "Origin": "https://www.firstcry.com",
    "X-Requested-With": "XMLHttpRequest"
}

# ======================
# APIS (1335 ONLY)
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

def send_discord(product,message):

    embed={
        "title":"Majorette Stock Monitor",
        "description":f"{message}\n\n👉 [Click here to Buy]({product['url']})",
        "color":16753920,
        "thumbnail":{"url":product["image"]},
        "fields":[
            {"name":"🏷 Product","value":product["name"],"inline":False},
            {"name":"💰 Price","value":f"₹{product['price']}","inline":True},
            {"name":"📦 Status","value":product["stock"],"inline":True},
            {"name":"🔢 Qty","value":str(product["qty"]),"inline":True}
        ],
        "footer":{"text":"FirstCry Monitor"}
    }

    payload={"embeds":[embed]}

    try:
        requests.post(WEBHOOK_URL,json=payload)
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

    print(f"{api['name']} Page {page} → {len(products)}")

    return products

# ======================
# PARSE PRODUCT
# ======================

def parse_product(p):

    pid=str(p.get("PId"))

    name=p.get("PNm","")
    brand=p.get("BNm","")

    qty=int(p.get("CrntStock",0))

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
        "stock":"In Stock" if qty>0 else "Out of Stock",
        "image":image,
        "url":url
    }

# ======================
# SCAN PRODUCTS
# ======================

def scan_products():

    products=[]

    with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:

        futures=[]

        for api in APIS:
            for page in range(1,8):
                futures.append(executor.submit(fetch_page,api,page))

        for f in futures:
            result=f.result()
            if result:
                products.extend(result)

    return products

# ======================
# MONITOR
# ======================

def monitor():

    db=load_db()

    print("Majorette monitor started")

    while True:

        try:

            products=scan_products()

            print("Total scanned:",len(products))

            for p in products:

                product=parse_product(p)
                pid=product["id"]

                if pid not in db:

                    send_discord(product,"🆕 New Product Detected")
                    db[pid]=product
                    continue

                old=db[pid]

                changes=[]

                if product["price"]!=old["price"]:
                    changes.append(f"💰 Price {old['price']} → {product['price']}")

                if old["qty"]==0 and product["qty"]>0:
                    changes.append(f"🚨 RESTOCK {old['qty']} → {product['qty']}")

                if product["qty"]!=old["qty"]:
                    changes.append(f"📦 Qty {old['qty']} → {product['qty']}")

                if changes:
                    send_discord(product,"\n".join(changes))

                db[pid]=product

            save_db(db)

        except Exception as e:
            print("Monitor error:",e)

        time.sleep(CHECK_INTERVAL)

# ======================
# START
# ======================

if __name__=="__main__":
    monitor()
