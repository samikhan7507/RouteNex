"""Shop catalogue: everyday things students and families really order. Pure data + one sync function (no web framework needed).

sync() is safe to run on every start:
  * items that are missing are added; items that exist (matched by name) get their text, price, icon and weight refreshed
  * stock is kept as it is (it changes with orders) - except in demo mode, where very low stock is topped up
  * the old, hard-to-understand demo services (LEGACY) are hidden, never deleted, so past orders still show their names
"""
import zlib

# category -> (starting stock, spread). Cheap daily things get more stock than a trolley bag.
STOCK = {"Stationery": (90, 60), "Books & Exam Prep": (40, 30), "Electronics & Accessories": (25, 25), "Engineering & Lab": (20, 20),
         "Hostel & Room": (30, 25), "Kitchen & Mess": (25, 20), "Groceries": (80, 70), "Snacks & Drinks": (70, 60),
         "Personal Care & Health": (60, 50), "Cleaning & Laundry": (60, 40), "Bags & Travel": (18, 15), "Art & Craft": (50, 40),
         "Sports & Fitness": (22, 18), "Print & Copy": (200, 100)}

# (category, name, description, price in Rs, weight in kg, icon)
ITEMS = [
    # ---- Stationery
    ("Stationery", "Ruled Notebook, A4 (200 pages)", "Sewn-binding ruled notebook for class notes", 89, 0.4, "📓"),
    ("Stationery", "Notebook Pack, Single Line (set of 6)", "Six 172-page notebooks for school or college", 279, 1.3, "📚"),
    ("Stationery", "Spiral Notebook, 5 Subject (300 pages)", "Subject dividers and perforated sheets", 169, 0.6, "🗒️"),
    ("Stationery", "Ball Pens, Blue (pack of 10)", "Smooth 0.7 mm ball pens for exams and daily writing", 60, 0.12, "🖊️"),
    ("Stationery", "Gel Pens, Assorted (pack of 12)", "Quick-dry gel ink in assorted colours", 149, 0.15, "🖋️"),
    ("Stationery", "Pencils HB with Eraser & Sharpener (set of 10)", "Pencil set for sketching and exams", 79, 0.15, "✏️"),
    ("Stationery", "Geometry Box (full set)", "Compass, divider, protractor and set squares", 129, 0.3, "📐"),
    ("Stationery", "Highlighters (pack of 5)", "Chisel-tip highlighters in five colours", 99, 0.12, "🖍️"),
    ("Stationery", "Sticky Notes (5 pads x 100 sheets)", "Bright reminder notes for desk and books", 120, 0.2, "📝"),
    ("Stationery", "Stapler with 1000 Pins", "Desk stapler with no. 10 pins", 110, 0.3, "📎"),
    ("Stationery", "Exam Clipboard with Pad", "A4 hard clipboard with a 50-sheet pad", 149, 0.35, "📋"),
    ("Stationery", "Plastic Folders, A4 (pack of 5)", "Snap-button folders for certificates and assignments", 149, 0.3, "🗂️"),
    ("Stationery", "Whiteboard Markers (pack of 4)", "Refillable markers in four colours", 120, 0.1, "✒️"),
    ("Stationery", "Rulers, 30 cm (pack of 3)", "Clear plastic rulers with cm and inch scales", 39, 0.1, "📏"),
    ("Stationery", "Paper Clips & Binder Clips Combo", "Assorted clips for papers and files", 59, 0.1, "🖇️"),
    ("Stationery", "Correction Tape (pack of 3)", "Clean, instant correction for notes and forms", 75, 0.08, "🩹"),
    # ---- Books & Exam Prep
    ("Books & Exam Prep", "Class 10 CBSE Sample Papers", "Board-pattern practice papers with solutions", 249, 0.5, "📘"),
    ("Books & Exam Prep", "Class 12 Physics Practice Workbook", "Chapter-wise questions with solutions", 329, 0.6, "📗"),
    ("Books & Exam Prep", "Class 12 Chemistry Practice Workbook", "Chapter-wise questions with solutions", 329, 0.6, "📗"),
    ("Books & Exam Prep", "Class 12 Mathematics Practice Workbook", "Chapter-wise questions with solutions", 329, 0.6, "📗"),
    ("Books & Exam Prep", "JEE Main Previous Years' Papers (10 years)", "Solved papers with topic-wise analysis", 599, 0.9, "🎯"),
    ("Books & Exam Prep", "NEET Previous Years' Papers (10 years)", "Solved papers with topic-wise analysis", 599, 0.9, "🎯"),
    ("Books & Exam Prep", "Quantitative Aptitude & Reasoning Guide", "Practice for placements and competitive exams", 349, 0.6, "🧮"),
    ("Books & Exam Prep", "Spoken English & Interview Guide", "Everyday speaking, group discussions and interviews", 199, 0.3, "🗣️"),
    ("Books & Exam Prep", "Concise English Dictionary", "Pocket dictionary with meanings and usage", 199, 0.5, "📖"),
    ("Books & Exam Prep", "English-Hindi Dictionary", "Two-way dictionary for school and college", 249, 0.6, "📖"),
    ("Books & Exam Prep", "Python Programming for Beginners", "Step-by-step basics with practice problems", 449, 0.5, "🐍"),
    ("Books & Exam Prep", "Data Structures & Algorithms Handbook", "Interview-style problems explained simply", 599, 0.7, "🧠"),
    ("Books & Exam Prep", "SQL & Database Basics", "Queries, joins and design for beginners", 399, 0.45, "🗄️"),
    ("Books & Exam Prep", "Rajasthan General Knowledge Handbook", "Useful for RPSC and other state exams", 299, 0.5, "🏛️"),
    ("Books & Exam Prep", "Current Affairs Yearbook", "Year-in-review for competitive exams", 349, 0.6, "📰"),
    # ---- Electronics & Accessories
    ("Electronics & Accessories", "USB-C Fast Charging Cable (1 m)", "Braided cable for phone and tablet charging", 199, 0.05, "🔌"),
    ("Electronics & Accessories", "20 W USB-C Wall Charger", "Fast charger for most modern phones", 599, 0.15, "⚡"),
    ("Electronics & Accessories", "Wired Earphones with Mic", "3.5 mm earphones for classes and calls", 249, 0.05, "🎧"),
    ("Electronics & Accessories", "Bluetooth Earbuds", "Wireless earbuds with charging case", 1299, 0.1, "🎵"),
    ("Electronics & Accessories", "Power Bank 10,000 mAh", "Dual-output power bank for the day", 1099, 0.25, "🔋"),
    ("Electronics & Accessories", "Pen Drive 32 GB", "USB 3.0 flash drive for notes and projects", 399, 0.02, "💾"),
    ("Electronics & Accessories", "Pen Drive 64 GB", "USB 3.0 flash drive for notes and projects", 649, 0.02, "💾"),
    ("Electronics & Accessories", "Memory Card 64 GB", "microSD card for phones and cameras", 549, 0.01, "🗃️"),
    ("Electronics & Accessories", "Wireless Mouse", "Silent-click mouse with USB receiver", 449, 0.1, "🖱️"),
    ("Electronics & Accessories", "USB Keyboard", "Full-size wired keyboard", 599, 0.5, "⌨️"),
    ("Electronics & Accessories", "Mouse Pad (large)", "Non-slip desk mat", 149, 0.15, "🟦"),
    ("Electronics & Accessories", "Laptop Sleeve, 15.6 inch", "Padded water-resistant sleeve", 499, 0.3, "💼"),
    ("Electronics & Accessories", "Foldable Laptop Stand", "Adjustable aluminium stand", 699, 0.6, "💻"),
    ("Electronics & Accessories", "Mobile Phone Stand", "Desk stand for video lectures", 199, 0.15, "📱"),
    ("Electronics & Accessories", "Extension Board, 4 Socket with Switch", "Surge-protected board with 1.5 m cord", 449, 0.6, "🔌"),
    ("Electronics & Accessories", "LED Rechargeable Desk Lamp", "Three brightness levels, USB charging", 799, 0.5, "💡"),
    ("Electronics & Accessories", "HDMI Cable (1.5 m)", "For laptop-to-monitor or TV", 249, 0.1, "📺"),
    ("Electronics & Accessories", "Webcam, 1080p", "Plug-and-play camera for online classes", 1499, 0.2, "📷"),
    ("Electronics & Accessories", "Table Fan, Small (3 speed)", "Compact fan for hostel desks", 1199, 2.0, "🌀"),
    ("Electronics & Accessories", "Screen Cleaning Kit", "Spray, cloth and brush for screens", 149, 0.1, "🧽"),
    # ---- Engineering & Lab
    ("Engineering & Lab", "Scientific Calculator (240+ functions)", "Allowed in most school and college exams", 949, 0.15, "🧮"),
    ("Engineering & Lab", "Engineering Drawing Mini Drafter Set", "Mini drafter, scales and set squares", 799, 0.9, "📐"),
    ("Engineering & Lab", "Graph Paper Pad, A4 (100 sheets)", "1 mm graph paper for plots and drawings", 90, 0.3, "📈"),
    ("Engineering & Lab", "Lab Coat, Cotton (unisex)", "Full-sleeve white lab coat", 399, 0.45, "🥼"),
    ("Engineering & Lab", "Safety Goggles", "Clear, scratch-resistant lab goggles", 149, 0.1, "🥽"),
    ("Engineering & Lab", "Digital Multimeter", "Voltage, current and resistance testing", 549, 0.3, "🔬"),
    ("Engineering & Lab", "Soldering Iron Kit", "Iron, stand, solder wire and flux", 599, 0.5, "🛠️"),
    ("Engineering & Lab", "Breadboard & Jumper Wire Kit", "830-point breadboard with 65 jumper wires", 249, 0.2, "🔩"),
    ("Engineering & Lab", "Arduino-Compatible Starter Kit", "Board, sensors, LEDs and project guide", 1299, 0.6, "🤖"),
    ("Engineering & Lab", "Wire Stripper & Cutter", "For electronics and project wiring", 199, 0.2, "✂️"),
    ("Engineering & Lab", "Digital Vernier Caliper", "150 mm caliper with LCD display", 449, 0.25, "📏"),
    # ---- Hostel & Room
    ("Hostel & Room", "Cotton Bedsheet Set, Single", "Fitted-style sheet with one pillow cover", 499, 0.9, "🛏️"),
    ("Hostel & Room", "Pillows (pack of 2)", "Soft fibre-filled pillows", 499, 1.0, "🛌"),
    ("Hostel & Room", "Fleece Blanket, Single", "Warm, light blanket for winter nights", 699, 1.4, "🧣"),
    ("Hostel & Room", "Mosquito Net, Single Bed", "Foldable net with hanging cords", 299, 0.4, "🦟"),
    ("Hostel & Room", "Bucket (16 L) with Mug", "Sturdy plastic bucket and mug", 199, 0.8, "🪣"),
    ("Hostel & Room", "Plastic Hangers (pack of 12)", "Non-slip hangers for shirts and tops", 149, 0.5, "👔"),
    ("Hostel & Room", "Folding Clothes Drying Stand", "Fits a small room or balcony", 799, 3.5, "🧺"),
    ("Hostel & Room", "Storage Box with Lid (30 L)", "Stackable box for books and clothes", 449, 1.2, "📦"),
    ("Hostel & Room", "Wall Clock", "Silent-sweep 12 inch wall clock", 299, 0.5, "🕒"),
    ("Hostel & Room", "Padlock Set (2 locks, 4 keys)", "Locks for cupboards and trunks", 249, 0.3, "🔒"),
    ("Hostel & Room", "Foldable Study Table", "Light table with laptop-friendly top", 1799, 5.0, "🪑"),
    ("Hostel & Room", "Door Mat", "Anti-slip absorbent door mat", 149, 0.5, "🚪"),
    ("Hostel & Room", "Wall Hooks (pack of 10)", "Adhesive hooks, no drilling needed", 99, 0.2, "🪝"),
    # ---- Kitchen & Mess
    ("Kitchen & Mess", "Electric Kettle, 1.5 L", "Auto switch-off kettle for tea, noodles and coffee", 699, 0.9, "☕"),
    ("Kitchen & Mess", "Steel Lunch Box (3 containers)", "Leak-proof tiffin with a carry bag", 399, 0.6, "🍱"),
    ("Kitchen & Mess", "Insulated Steel Bottle, 1 L", "Keeps drinks hot or cold for hours", 549, 0.4, "🍶"),
    ("Kitchen & Mess", "Steel Tumblers (set of 4)", "Easy-grip stainless steel tumblers", 299, 0.5, "🥛"),
    ("Kitchen & Mess", "Plates & Bowls Set (12 pieces)", "Unbreakable dinner set for four", 599, 2.0, "🍽️"),
    ("Kitchen & Mess", "Cutlery Set, Steel (24 pieces)", "Spoons, forks and knives", 349, 0.8, "🍴"),
    ("Kitchen & Mess", "Induction Cooktop, 1800 W", "Push-button cooktop for hostel cooking", 1799, 2.5, "🍳"),
    ("Kitchen & Mess", "Pressure Cooker, 3 L", "Aluminium cooker for rice and dal", 1099, 2.0, "🥘"),
    ("Kitchen & Mess", "Non-stick Pan, 24 cm", "Induction-friendly pan", 599, 1.0, "🍳"),
    ("Kitchen & Mess", "Sandwich Maker", "Grill plates for quick breakfasts", 999, 1.5, "🥪"),
    # ---- Groceries
    ("Groceries", "Rice, 5 kg", "Everyday long-grain rice", 320, 5.0, "🍚"),
    ("Groceries", "Wheat Flour (Atta), 5 kg", "Whole-wheat chakki atta", 260, 5.0, "🌾"),
    ("Groceries", "Toor Dal, 1 kg", "Clean, polished arhar dal", 165, 1.0, "🫘"),
    ("Groceries", "Moong Dal, 1 kg", "Split yellow moong dal", 140, 1.0, "🫘"),
    ("Groceries", "Cooking Oil, 1 L", "Refined sunflower oil", 155, 0.95, "🫗"),
    ("Groceries", "Sugar, 1 kg", "Fine-grain sugar", 48, 1.0, "🍬"),
    ("Groceries", "Salt, 1 kg", "Iodised table salt", 25, 1.0, "🧂"),
    ("Groceries", "Tea, 500 g", "Strong CTC tea leaves", 250, 0.5, "🍵"),
    ("Groceries", "Instant Coffee, 100 g", "Classic instant coffee powder", 320, 0.15, "☕"),
    ("Groceries", "Oats, 1 kg", "Rolled oats for quick breakfasts", 190, 1.0, "🥣"),
    ("Groceries", "Poha, 1 kg", "Thick flattened rice", 80, 1.0, "🍛"),
    ("Groceries", "Peanut Butter, 500 g", "Creamy, high-protein spread", 250, 0.55, "🥜"),
    ("Groceries", "Eggs (tray of 30)", "Farm-fresh white eggs", 210, 1.9, "🥚"),
    ("Groceries", "Milk, 1 L (pack of 4)", "Toned milk packets", 280, 4.2, "🥛"),
    ("Groceries", "Bread & Butter Combo", "Sandwich bread loaf with salted butter", 90, 0.6, "🍞"),
    ("Groceries", "Seasonal Fruits, 1 kg", "Fresh fruit picked for the week", 150, 1.0, "🍎"),
    ("Groceries", "Bananas (1 dozen)", "Ripe yellow bananas", 70, 1.2, "🍌"),
    ("Groceries", "Mixed Vegetables, 2 kg", "Potato, onion, tomato and greens", 120, 2.0, "🥦"),
    # ---- Snacks & Drinks
    ("Snacks & Drinks", "Instant Noodles (pack of 12)", "Masala noodles for late-night study", 168, 1.0, "🍜"),
    ("Snacks & Drinks", "Biscuits, Family Pack (6 packets)", "Tea-time biscuits", 120, 0.8, "🍪"),
    ("Snacks & Drinks", "Namkeen Mix, 1 kg", "Crunchy savoury mix", 260, 1.0, "🥨"),
    ("Snacks & Drinks", "Chocolate Gift Box", "Assorted chocolates for celebrations", 199, 0.3, "🍫"),
    ("Snacks & Drinks", "Dry Fruits Mix, 500 g", "Almonds, cashews, raisins and walnuts", 520, 0.5, "🌰"),
    ("Snacks & Drinks", "Protein Bars (box of 6)", "Filling bars for gym and exams", 499, 0.4, "💪"),
    ("Snacks & Drinks", "Soft Drinks, 600 ml (pack of 6)", "Chilled-style fizzy drinks", 270, 3.8, "🥤"),
    ("Snacks & Drinks", "Fruit Juice, 1 L (pack of 4)", "Ready-to-drink mixed fruit juice", 380, 4.2, "🧃"),
    ("Snacks & Drinks", "Packaged Water, 1 L (pack of 12)", "Sealed drinking water bottles", 180, 12.0, "💧"),
    ("Snacks & Drinks", "Drinking Water Jar, 20 L", "Sealed 20-litre jar for hostel rooms", 90, 21.0, "🚰"),
    # ---- Personal Care & Health
    ("Personal Care & Health", "Hand Sanitizer, 500 ml", "Alcohol-based pump bottle", 199, 0.55, "🧴"),
    ("Personal Care & Health", "Soap Bars (pack of 4)", "Gentle bathing soap", 140, 0.5, "🧼"),
    ("Personal Care & Health", "Shampoo, 340 ml", "Daily-use shampoo", 275, 0.4, "🧴"),
    ("Personal Care & Health", "Toothpaste & Toothbrush Combo", "Fluoride paste with soft brush", 149, 0.25, "🪥"),
    ("Personal Care & Health", "Face Wash, 100 ml", "Oil-control face wash", 199, 0.15, "🧴"),
    ("Personal Care & Health", "Sunscreen SPF 50, 100 ml", "Non-greasy sun protection", 349, 0.15, "☀️"),
    ("Personal Care & Health", "Deodorant, 150 ml", "Long-lasting body spray", 199, 0.2, "🌬️"),
    ("Personal Care & Health", "Body Lotion, 400 ml", "Light moisturiser for dry skin", 299, 0.45, "🧴"),
    ("Personal Care & Health", "First Aid Kit", "Bandages, antiseptic wipes and basics", 349, 0.5, "🩹"),
    ("Personal Care & Health", "Digital Thermometer", "Fast, accurate temperature check", 199, 0.05, "🌡️"),
    ("Personal Care & Health", "Surgical Face Masks (box of 50)", "3-layer disposable masks", 149, 0.3, "😷"),
    ("Personal Care & Health", "Sanitary Pads, XL (pack of 30)", "Soft, high-absorption pads", 249, 0.5, "🌸"),
    # ---- Cleaning & Laundry
    ("Cleaning & Laundry", "Detergent Powder, 2 kg", "Machine and hand-wash powder", 260, 2.0, "🧺"),
    ("Cleaning & Laundry", "Dish-wash Liquid, 750 ml", "Lemon dish-wash liquid", 140, 0.8, "🍋"),
    ("Cleaning & Laundry", "Floor Cleaner, 1 L", "Disinfectant floor cleaner", 160, 1.1, "🧴"),
    ("Cleaning & Laundry", "Toilet Cleaner, 500 ml", "Thick toilet cleaner", 110, 0.55, "🚽"),
    ("Cleaning & Laundry", "Garbage Bags (pack of 30)", "Medium-size dustbin liners", 99, 0.3, "🗑️"),
    ("Cleaning & Laundry", "Broom & Dustpan Set", "Soft broom with dustpan", 249, 0.8, "🧹"),
    ("Cleaning & Laundry", "Laundry Basket", "Ventilated folding basket", 249, 0.7, "🧺"),
    ("Cleaning & Laundry", "Tissue Rolls (pack of 6)", "Soft 2-ply tissue rolls", 199, 0.6, "🧻"),
    ("Cleaning & Laundry", "Scrub Pads (pack of 6)", "Kitchen scrub pads", 70, 0.1, "🧽"),
    # ---- Bags & Travel
    ("Bags & Travel", "College Backpack, 30 L", "Padded straps, three compartments", 899, 0.7, "🎒"),
    ("Bags & Travel", "Laptop Backpack with USB Port", "Fits up to 15.6 inch laptops", 1299, 0.9, "💻"),
    ("Bags & Travel", "Cabin Trolley Bag", "Hard-shell bag with 360 degree wheels", 2499, 3.0, "🧳"),
    ("Bags & Travel", "Duffel Bag", "Roomy bag for weekend trips", 799, 0.8, "👜"),
    ("Bags & Travel", "Travel Neck Pillow & Eye Mask", "Comfort set for long journeys", 349, 0.3, "😴"),
    ("Bags & Travel", "Umbrella, Foldable", "Compact 3-fold umbrella", 349, 0.4, "☂️"),
    ("Bags & Travel", "Rain Poncho", "Lightweight reusable poncho", 199, 0.3, "🌧️"),
    ("Bags & Travel", "Luggage Strap & Tag Set", "Adjustable strap with ID tag", 199, 0.2, "🏷️"),
    # ---- Art & Craft
    ("Art & Craft", "Drawing Book, A3 (40 pages)", "Thick drawing paper", 99, 0.3, "🎨"),
    ("Art & Craft", "Colour Pencils, 48 Shades", "Smooth, vibrant colours", 299, 0.3, "🖍️"),
    ("Art & Craft", "Water Colour Set (24 shades) with Brushes", "For school art and projects", 249, 0.4, "🖌️"),
    ("Art & Craft", "Sketch Pens (24 colours)", "Washable fibre-tip pens", 199, 0.2, "🖊️"),
    ("Art & Craft", "Chart Papers (pack of 10)", "Assorted colour chart sheets", 120, 0.5, "📄"),
    ("Art & Craft", "Glue Sticks (pack of 4)", "Non-toxic paper glue", 80, 0.15, "🧴"),
    ("Art & Craft", "Scissors & Cutter Combo", "Safe-grip scissors and paper cutter", 99, 0.2, "✂️"),
    ("Art & Craft", "Foam Board Sheets, A2 (pack of 3)", "Sturdy boards for models and posters", 199, 0.7, "🧱"),
    ("Art & Craft", "Project Model-making Kit", "Craft sticks, clay, paints and glue", 349, 0.8, "🧩"),
    # ---- Sports & Fitness
    ("Sports & Fitness", "Badminton Rackets (pair) with 3 Shuttles", "Lightweight rackets for hostel courts", 699, 0.6, "🏸"),
    ("Sports & Fitness", "Football, Size 5", "Stitched ball for turf and ground", 599, 0.45, "⚽"),
    ("Sports & Fitness", "Cricket Tennis Balls (pack of 6)", "Durable balls for gully cricket", 210, 0.6, "🏏"),
    ("Sports & Fitness", "Yoga Mat, 6 mm", "Non-slip cushioned mat", 499, 1.1, "🧘"),
    ("Sports & Fitness", "Skipping Rope", "Adjustable speed rope", 149, 0.2, "🪢"),
    ("Sports & Fitness", "Dumbbell Pair, 5 kg", "Rubber-coated hex dumbbells", 799, 5.0, "🏋️"),
    ("Sports & Fitness", "Resistance Band Set", "Five bands for home workouts", 349, 0.5, "💪"),
    ("Sports & Fitness", "Sipper Bottle, 750 ml", "BPA-free gym bottle", 249, 0.2, "🥤"),
    ("Sports & Fitness", "Running Socks (pack of 3)", "Cushioned breathable socks", 199, 0.15, "🧦"),
    # ---- Print & Copy
    ("Print & Copy", "Black & White Printout (50 pages)", "Clear laser prints, A4", 100, 0.25, "🖨️"),
    ("Print & Copy", "Colour Printout (20 pages)", "Colour prints for projects and posters", 200, 0.1, "🖨️"),
    ("Print & Copy", "Spiral Binding (up to 100 pages)", "Neat spiral binding with covers", 60, 0.1, "🔗"),
    ("Print & Copy", "Passport Photos (set of 8)", "Studio-quality photos for forms and ID", 120, 0.02, "🪪"),
    ("Print & Copy", "Project Report Print + Hard Binding (100 pages)", "Printed and bound with a hard cover", 450, 0.8, "📑"),
    ("Print & Copy", "Lamination, A4 (5 sheets)", "Gloss lamination for certificates", 75, 0.1, "🪟"),
]

# The previous demo "services" - hidden from the shop (not deleted) so old orders keep their item names.
LEGACY = ["Express Parcel", "Same-Day Documents", "Grocery Essentials Box", "Pharmacy Express", "Cold Chain Crate", "Home Move Mini", "Home Move Plus",
          "Electronics Secure", "Fragile Art Pack", "Bulk Business Van", "Two-Wheeler Tow", "Airport Luggage", "Furniture Delivery",
          "Food Partner Sprint", "Daily Delivery Pass"]

CATEGORIES = list(dict.fromkeys(i[0] for i in ITEMS))
WEIGHTS = {name: kg for _, name, _, _, kg, _ in ITEMS}


def stock_for(category, name):
    base, spread = STOCK.get(category, (30, 20))
    return base + zlib.crc32(name.encode("utf-8")) % spread        # deterministic, so every deploy starts with the same stock


def seed_rows():
    """(name, description, category, price, stock, icon) in catalogue order - used by database/seed.py."""
    return [(name, desc, cat, price, stock_for(cat, name), icon) for cat, name, desc, price, _, icon in ITEMS]


def sync():
    """Bring the items table in line with ITEMS. Returns how many items were added."""
    import config
    from db import tx
    added = 0
    with tx() as c:
        have = {r["name"]: r["id"] for r in c.execute("SELECT id,name FROM items")}
        for cat, name, desc, price, kg, icon in ITEMS:
            if name in have:
                c.execute("UPDATE items SET description=?,category=?,price=?,icon=?,weight_kg=?,active=1 WHERE id=?", (desc, cat, price, icon, kg, have[name]))
                if config.DEMO_MODE:                                  # public demo: never let a popular item sit at zero forever
                    c.execute("UPDATE items SET stock=? WHERE id=? AND stock<5", (stock_for(cat, name), have[name]))
            else:
                c.execute("INSERT INTO items(name,description,category,price,stock,icon,weight_kg,active) VALUES(?,?,?,?,?,?,?,1)", (name, desc, cat, price, stock_for(cat, name), icon, kg))
                added += 1
        for name in LEGACY:
            c.execute("UPDATE items SET active=0 WHERE name=?", (name,))
    if added:
        print(f"[catalog] added {added} items")
    return added
