
import requests
import time
import json
import os

WEBHOOK_URL = "https://discord.com/api/webhooks/1479454664809386088/STcConwFImwGLctUM0Yg_jOuzn_POphiPeWv_5xTyydxS3P6ZVziws_KknNX3D41ftuW"
CHECK_INTERVAL = 2

BASE_URL = "https://www.firstcry.com/svcs/SearchResult.svc/GetSearchResultProductsPaging"

PARAMS = {
    "PageNo": 1,
    "PageSize": 20,
    "SortExpression": "NewArrivals",
    "OnSale": 0,
    "SearchString": "brand",
    "MasterBrand": 1335,
    "pcode": 600119,
    "isclub": 1
}

DATA_FILE = "database.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json"
}

session = requests.Session()
session.headers.update(HEADERS)


def load_database():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE) as f:
            return json.load(f)
    return {}


def save_database(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f)


def send_discord(product, message):

    embed = {
        "title": product["name"],
        "url": product["url"],
        "description": message,
        "thumbnail": {"url": product["image"]},
        "color": 16753920,
        "fields": [
            {"name": "Price", "value": f"₹{product['price']}", "inline": True},
            {"name": "Old Price", "value": f"₹{product['old_price']}", "inline": True},
            {"name": "Stock", "value": product["stock"], "inline": True},
            {"name": "Quantity", "value": str(product["qty"]), "inline": True}
        ]
    }

    payload = {"embeds": [embed]}

    requests.post(WEBHOOK_URL, json=payload)


def fetch_page(page):

    PARAMS["PageNo"] = page

    r = session.get(BASE_URL, params=PARAMS)

    data = r.json()

    return data.get("products", [])


def parse_product(p):

    return {
        "id": str(p.get("SKU")),
        "name": p.get("ProductName"),
        "price": p.get("Price"),
        "old_price": p.get("OldPrice"),
        "qty": p.get("AvailableQuantity", 0),
        "stock": "In Stock" if p.get("AvailableQuantity", 0) > 0 else "Out of Stock",
        "image": "https:" + p.get("ImagePath", ""),
        "url": "https://www.firstcry.com" + p.get("ProductUrl", "")
    }


def monitor():

    db = load_database()

    print("FirstCry monitor started...")

    while True:

        try:

            page = 1

            while True:

                products = fetch_page(page)

                if not products:
                    break

                for p in products:

                    product = parse_product(p)

                    pid = product["id"]

                    if pid not in db:

                        send_discord(product, "🆕 New Product Detected")

                        db[pid] = product
                        continue

                    old = db[pid]

                    changes = []

                    if product["price"] != old["price"]:
                        changes.append(
                            f"💰 Price Changed: ₹{old['price']} → ₹{product['price']}"
                        )

                    if product["stock"] != old["stock"]:
                        changes.append(
                            f"📦 Stock Changed: {old['stock']} → {product['stock']}"
                        )

                    if old["qty"] == 0 and product["qty"] > 0:
                        changes.append(
                            f"🚨 RESTOCK! Qty: {old['qty']} → {product['qty']}"
                        )

                    if product["qty"] != old["qty"]:
                        changes.append(
                            f"🔢 Quantity: {old['qty']} → {product['qty']}"
                        )

                    if changes:
                        send_discord(product, "\n".join(changes))

                    db[pid] = product

                page += 1

            save_database(db)

        except Exception as e:
            print("Error:", e)

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    monitor()
