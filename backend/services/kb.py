"""Tiny retrieval-augmented FAQ: pure-Python BM25 over hand-written, code-accurate policy passages (no embeddings, no downloads)."""
import math, re

PASSAGES = [
    ("cancel-trip", "Cancelling a ride or parcel", "You can cancel a ride or parcel while we are finding a driver or while the driver is on the way, free of charge. After the driver has arrived, a prepaid booking is charged a Rs 20 cancellation fee and the rest is refunded. Open the trip and tap Cancel. Refunds go to your RouteNex wallet instantly.", "cancel cancellation fee refund ride parcel trip"),
    ("cancel-order", "Cancelling a shop order", "A shop order can be cancelled until the driver picks it up. Stock is released, any prepaid amount is refunded to your wallet and the order is removed from its route. Once an order is out for delivery it can no longer be cancelled.", "cancel order shop refund picked up"),
    ("otp", "OTP codes", "Rides use a 4-digit start OTP that you give the driver at pickup. Parcels have two OTPs: a pickup OTP for the driver and a delivery OTP that the recipient gives the driver at drop-off. After 5 wrong attempts a trip is temporarily locked. Never share OTPs with anyone except the driver on your trip.", "otp code pin verify start delivery safety"),
    ("payments", "Payment methods", "You can pay with cash (or cash on delivery for shop orders), your RouteNex wallet, UPI or card. In this demo build UPI and card are simulated and no real money moves. Wallet balance and refunds are tracked in a real ledger.", "payment pay upi card cash wallet cod method"),
    ("refund", "Refunds", "Refunds for cancelled or timed-out bookings go back to your RouteNex wallet immediately. You can see them under Wallet, in Transactions.", "refund money back wallet cancelled"),
    ("wallet", "Wallet and top-up", "Open Wallet to see your balance, add money (demo UPI) and view every transaction. You can pay for rides, parcels and shop orders from the wallet if the balance is enough.", "wallet balance top up add money transactions"),
    ("coupons", "Coupons and offers", "Enter a coupon code when booking or at checkout. Some codes are one-time, some need a minimum amount, and each works only for rides, parcels or shop orders as stated. If you cancel a booking, the coupon is given back. Ask me 'what offers do I have' to see the live list.", "coupon offer discount promo code"),
    ("surge", "Why the price changed (demand pricing)", "Fares rise a little when many people are requesting trips and few drivers are free, and at busy hours. The booking screen shows it as, for example, 1.2x demand. A forecast of the coming hour can nudge the price by at most 10 percent.", "surge price higher demand peak dynamic pricing"),
    ("eta", "How ETAs are calculated", "ETAs come from a trained model that looks at distance, time of day, area traffic, weather and load. Under each option you may see reasons such as Heavy traffic +4 min or Rain +2 min.", "eta time arrival estimate traffic rain minutes how long"),
    ("no-driver", "No driver found", "We keep looking for up to 90 seconds. If no driver accepts, the booking is cancelled automatically and any prepaid amount is refunded to your wallet. You can try again or choose another vehicle type.", "no driver found searching waiting not matched"),
    ("parcel-rules", "Parcel sizes and prices", "Bike courier carries up to 10 kg, Mini cargo up to 150 kg and Van up to 900 kg. Price depends on distance, weight, size and demand; marking a parcel fragile adds Rs 25. You must give the recipient's name and 10-digit phone number.", "parcel weight kg size fragile courier limit van bike price"),
    ("delivery-windows", "Delivery windows and priority", "For shop orders you choose a delivery window and a priority (standard, priority, critical). Our route planner serves overdue and high-priority orders first and tells dispatchers which stops are at risk of being late.", "delivery window priority late schedule slot"),
    ("driver-earnings", "Driver earnings", "Drivers earn 80 percent of the fare for each completed trip. Earnings for today, the last 7 days and all time are on the Driver Console.", "driver earnings earn money payout share commission"),
    ("rating", "Ratings", "After a completed trip you can rate the driver from 1 to 5 stars and leave a comment. Ratings update the driver's average.", "rating rate review stars feedback"),
    ("privacy", "Privacy", "Your phone number is shared only with the driver assigned to your trip. The assistant can only see your own account data, and it cannot book, cancel or change anything until you press Confirm.", "privacy data phone safe security assistant"),
    ("demo", "About this app", "RouteNex is a capstone demo: drivers are simulated, UPI and card are mock payments, and ML models are trained on synthetic data. Weather is live and fleet data is real inside the app.", "demo about capstone simulated mock synthetic"),
]
_STOP = set("a an the is are was were to of in on for and or my me i you it do does how what why can when where which with this that be at as from by tell give show please want need know ok hi hello kab".split())


def _tok(t):
    return [w[:-1] if len(w) > 3 and w.endswith("s") else w for w in re.findall(r"[a-z0-9]+", t.lower()) if w not in _STOP]


_DOCS = [(p, _tok(p[1] + " " + p[1] + " " + p[2] + " " + p[3])) for p in PASSAGES]
_AVG = sum(len(d) for _, d in _DOCS) / len(_DOCS)
_DF = {}
for _, d in _DOCS:
    for w in set(d):
        _DF[w] = _DF.get(w, 0) + 1


def search(q, k=2, min_score=1.2):
    """-> [(score, id, title, text)] best first (only passages above min_score)."""
    qt = _tok(q); out = []
    for (pid, title, text, _), d in _DOCS:
        s = 0.0
        for w in qt:
            f = d.count(w)
            if f:
                idf = math.log(1 + (len(_DOCS) - _DF[w] + 0.5) / (_DF[w] + 0.5))
                s += idf * f * 2.5 / (f + 1.5 * (0.25 + 0.75 * len(d) / _AVG))
        if s >= min_score:
            out.append((round(s, 2), pid, title, text))
    return sorted(out, reverse=True)[:k]
