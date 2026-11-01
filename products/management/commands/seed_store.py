"""
Load the StepUp catalogue (categories, brands, styles, colours, 44 products with
size/colour stock, hero banners) from the supplied design images.

    python manage.py seed_store            # create anything missing
    python manage.py seed_store --reset    # wipe catalogue first (orders are kept)
"""
import random
from decimal import Decimal
from pathlib import Path

from django.core.files import File
from django.core.management.base import BaseCommand
from django.db import transaction

from products.models import (Banner, Brand, Category, Color, Product, ProductImage, ProductVariant, Style)

ASSETS = Path(__file__).resolve().parents[3] / "seed_assets"

COLORS = {
    "Black": "#000000", "Brown": "#7A5656", "White": "#FFFFFF", "Lavender": "#6F73B0", "Silver": "#9C9CAE",
    "Beige": "#CDB79E", "Grey": "#C4C4C4", "Tan": "#C49A6C", "Red": "#E21C1C", "Navy": "#1E4A8A",
    "Rust": "#8B2E16", "Denim Blue": "#8FA3C8", "Lilac": "#A9A9F0", "Pink": "#D98AA8", "Baby Pink": "#F2C6DD",
    "Sky Blue": "#A6CDF5", "Purple": "#9B4FE0", "Mauve": "#A5A0D0", "Blush": "#E8C4C0", "Gold": "#D6A35C",
    "Multi-color": "",
}

STYLES = ["Sandals", "Trainers", "Canvas", "Shoes", "Safety Footwear", "Boots", "Slippers", "Heels"]

SIZES = {"womens": ["36", "37", "38", "39", "40", "41"], "mens": ["41", "42", "43", "44", "45"],
         "kids": ["28", "29", "30", "31", "32", "33"]}

# (file, category, brand, name, style, price, rating, colours, trending, discount)
PRODUCTS = [
    # ---- Womens -------------------------------------------------------------------------------
    ("tancy-womens-lilac-sandal.png", "womens", "Lunar", "Tancy Womens Lilac Sandal", "Sandals", 2799, 5, ["Black", "Brown", "White"], False, None),
    ("drew-womens-diamante-slip-shoe.png", "womens", "Lilley", "Drew Womens Diamante Slip Shoe", "Shoes", 3799, 5, ["Black", "White"], False, None),
    ("selina-womens-navy-sandal.png", "womens", "Softlites", "Selina Womens Navy Sandal", "Sandals", 2699, 4, ["Black", "Brown", "White"], False, None),
    ("sadie-womens-floral-beach-mule.png", "womens", "shoezone", "Sadie Womens Floral Beach Mule", "Slippers", 2799, 5, ["Black", "Brown", "Lavender"], False, 1999),
    ("ophelia-womens-silver-heel.png", "womens", "Truffle", "Ophelia Womens Silver Heel", "Heels", 5999, 5, ["Silver"], False, None),
    ("audrey-womens-patent-lace-shoe.png", "womens", "Lilley", "Audrey Womens Patent Lace Shoe", "Shoes", 3799, 5, ["Black", "Brown", "White"], False, None),
    ("noelle-mesh-bow-ballerinas.png", "womens", None, "Noelle Mesh Bow Ballerinas", "Shoes", 3599, 4, ["Black", "Brown"], False, None),
    ("stella-flat-embellished-sliders.png", "womens", None, "Stella Flat Embellished Sliders", "Sandals", 1999, 4, ["Black", "Brown", "White"], False, None),
    ("olivia-pencil-heels.png", "womens", None, "Olivia Pencil Heels", "Heels", 3199, 5, ["Black"], False, None),
    ("amelia-kitten-heels.png", "womens", None, "Amelia Kitten Heels", "Heels", 3699, 4, ["Beige"], False, 2599),
    ("beckett-sandals.png", "womens", None, "Beckett Sandals", "Sandals", 2599, 5, ["Black", "Grey", "White"], False, None),
    ("gitano-flat-back-elastic-sandals.png", "womens", None, "Gitano Flat Back Elastic Sandals", "Sandals", 1799, 4, ["Gold"], False, None),
    # ---- Mens ---------------------------------------------------------------------------------
    ("harlan-mens-tan-boat-shoe.png", "mens", "Comfy Steps", "Harlan Mens Tan Boat Shoe", "Shoes", 2799, 5, ["Black", "Tan", "Red"], False, None),
    ("weaver-mens-lace-up-trainer.png", "mens", "XL", "Weaver Mens Lace Up Trainer", "Trainers", 1799, 5, ["Black", "Red", "White"], False, None),
    ("doubal-strap-sandals.png", "mens", None, "Doubal Strap Sandals", "Sandals", 2999, 4, ["Black", "Brown", "White"], False, None),
    ("lustral-white-leather-slippers.png", "mens", "Comfy Steps", "Lustral White Leather Slippers", "Slippers", 1995, 5, ["Brown", "White"], False, None),
    ("neptune-mens-lace-up-trainer.png", "mens", "Osaga", "Neptune Mens Lace Up Trainer", "Trainers", 2799, 5, ["Black", "Navy", "White"], False, None),
    ("mateo-leather-lace-up-sneakers.png", "mens", None, "Mateo Leather Lace-up Sneakers", "Shoes", 3999, 5, ["Black", "Brown", "White"], False, None),
    ("beaumont-mens-black-warm-boots.png", "mens", "Urban Territory", "Beaumont Mens Black Warm Boots", "Boots", 2799, 5, ["Black", "Brown", "White"], False, None),
    ("bill-mens-brown-lace-up-boot.png", "mens", "Urban Territory", "Bill Mens Brown Lace Up Boot", "Boots", 2999, 4, ["Black", "Brown"], False, 2399),
    ("leather-ethnic-sandals.png", "mens", None, "Leather Ethnic Sandals", "Sandals", 2995, 4, ["Brown"], False, None),
    ("herfa-hand-painted-tan-leather-sandals.png", "mens", None, "Herfa Hand Painted Tan Leather Sandals", "Sandals", 4999, 4, ["Brown"], False, None),
    ("lucas-luxury-leather-loafers.png", "mens", None, "Lucas Luxury Leather Loafers", "Shoes", 9999, 5, ["Black", "Brown"], False, 7999),
    ("lenore-tan-leather-formal-loafers.png", "mens", None, "Lenore Tan Leather Formal Loafers", "Shoes", 7399, 5, ["Rust"], False, None),
    # ---- Kids ---------------------------------------------------------------------------------
    ("whitby-girls-white-multi-marble-eva-clog.png", "kids", None, "Whitby Girls White Multi Marble EVA Clog", "Sandals", 2799, 4, ["Multi-color"], False, None),
    ("claudia-girls-blue-fasten-canvas.png", "kids", "Walkright", "Claudia Girls Blue Fasten Canvas", "Canvas", 3199, 4, ["Denim Blue"], False, None),
    ("carey-girls-pink-polka-dot-canvas.png", "kids", "Walkright", "Carey Girls Pink Polka Dot Canvas", "Canvas", 2699, 4, ["Lilac", "Pink"], False, None),
    ("charlotte-girls-multi-t-bar-sandal.png", "kids", "Walkright", "Charlotte Girls Multi T-Bar Sandal", "Sandals", 4799, 5, ["Multi-color"], False, 2399),
    ("cherish-girls-pink-bootie.png", "kids", "The Slipper Company", "Cherish Girls Pink Bootie", "Slippers", 2999, 4, ["Baby Pink"], False, None),
    ("surprise-kids-fasten-slipper.png", "kids", "LOL", "Surprise Kids Fasten Slipper", "Slippers", 2799, 5, ["Multi-color"], False, None),
    ("kids-blue-easy-fasten-slipper.png", "kids", "Bluey", "Kids Blue Easy Fasten Slipper", "Slippers", 4999, 4, ["Sky Blue"], False, None),
    ("kids-red-light-up-trainer.png", "kids", "Spider-Man", "Kids Red Light Up Trainer", "Trainers", 5799, 4, ["Multi-color"], False, 2899),
    ("fairground-kids-multi-eva-clog.png", "kids", "Disney Stitch", "Fairground Kids Multi EVA Clog", "Sandals", 3999, 5, ["Multi-color"], False, None),
    ("sparkle-kids-purple-sandal.png", "kids", "Disney Frozen", "Sparkle Kids Purple Sandal", "Sandals", 5599, 4, ["Purple"], False, None),
    ("shower-kids-black-welly.png", "kids", "shoezone", "Shower Kids Black Welly", "Boots", 4999, 5, ["Black", "Brown", "White"], False, None),
    ("hurricane-glitter-unicorn-welly.png", "kids", "shoezone", "Hurricane Glitter Unicorn Welly", "Boots", 2799, 4, ["Mauve"], False, None),
    # ---- New & Trending (home page) ----------------------------------------------------------
    ("ophelia-womens-silver-diamante-heel.jpg", "womens", "Truffle", "Ophelia Womens Silver Diamante Heel", "Heels", 2299, 5, ["Silver"], True, None),
    ("billie-womens-silver-diamante-heel.jpg", "womens", "Truffle", "Billie Womens Silver Diamante Heel", "Heels", 3000, 4, ["Silver"], True, None),
    ("drew-womens-blush-diamante-slip-on-shoe.jpg", "womens", "Lilley", "Drew Womens Blush Diamante Slip On Shoe", "Shoes", 2599, 5, ["Blush"], True, None),
    ("drew-womens-navy-diamante-slip-on-shoe.jpg", "womens", "Lilley", "Drew Womens Navy Diamante Slip On Shoe", "Shoes", 1299, 4, ["Navy"], True, None),
    ("weaver-mens-navy-lace-up-trainer.jpg", "mens", "XL", "Weaver Mens Navy Lace Up Trainer", "Trainers", 2799, 5, ["Navy"], True, None),
    ("weaver-mens-white-lace-up-trainer.jpg", "mens", "XL", "Weaver Mens White Lace Up Trainer", "Trainers", 2259, 4, ["White"], True, None),
    ("calista-girls-pink-daisy-print-sandal.jpg", "kids", "Walkright", "Calista Girls Pink Daisy Print Sandal", "Sandals", 2899, 5, ["Pink"], True, None),
    ("colby-boys-blue-dinosaur-canvas.jpg", "kids", "Walkright", "Colby Boys Blue Dinosaur Canvas", "Canvas", 3299, 4, ["Sky Blue"], True, None),
]

DESCRIPTIONS = {
    "Harlan Mens Tan Boat Shoe": (
        "The Harlan men's boat shoes from Comfy Steps are perfect for your casual summer outings. Featuring a "
        "tan upper with navy blue accents and intricate white stitching, these shoes offer a trendy look. The "
        "twin elasticated gussets and lace up fastening ensures a quick and secure fit, while the gripped "
        "outsole provides stability and security."
    ),
}

STYLE_COPY = {
    "Sandals": "an open, breathable design with a cushioned footbed for all-day wear",
    "Trainers": "a lightweight, flexible sole and padded collar for everyday comfort",
    "Canvas": "a soft canvas upper and easy fastening that little feet love",
    "Shoes": "a smart, versatile upper that pairs easily with casual and dressy looks",
    "Boots": "a sturdy upper and gripped outsole that keeps you steady in any weather",
    "Slippers": "a cosy lining and soft sole made for relaxed days at home",
    "Heels": "a flattering silhouette and a stable heel that's comfortable from day to night",
    "Safety Footwear": "a protective build designed for work environments",
}

CATEGORIES = [
    ("Womens", "womens", "Heels, sandals, flats and trainers for every occasion.", "womens.png", 1),
    ("Mens", "mens", "Boat shoes, trainers, boots, loafers and sandals.", "mens.png", 2),
    ("Kids", "kids", "Fun, comfortable shoes for growing feet.", "kids.png", 3),
]

BANNERS = [
    ("Flat 50% Sale — kids shoes", "hero-colourful-sneakers.jpg", "/offers"),
    ("Womens High Heels — Flat 30% offer for your first order", "hero-silver-heels.jpg", "/shop/womens?style=heels"),
    ("Men’s wear high heel office shoe only 40% discount today only", "hero-leather-loafers.jpg", "/shop/mens?style=shoes"),
    ("Womens red color — high heel for party — for your first order get a free gift", "hero-red-high-heels.jpg", "/shop/womens?style=heels"),
]

EXTRA_BRANDS = ["Barbie", "Beckett", "Comfort Plus", "Crocs", "Cushion Walk", "Disney Frozen", "Divaz",
                "Dunlop", "EarthWorks", "Gabbys Dollhouse", "Heart", "Heavenly Feet", "Hobos", "Hush Puppies",
                "Jo& Joe", "JuJu", "Kickers", "Krush", "Lambretta", "LoL", "Lotus", "Marco", "Lozzi", "Marvel",
                "Maya", "Grace", "Original Penguin", "Paw Patrol", "Pokemon", "Red Fish", "Red Level", "Regatta",
                "Rieker", "Rocket Dog", "Skechers", "Soft Line", "Stone Creek", "Super Mario", "Totes Isotoner",
                "Trespass", "Trux", "Umbro", "Wednesday", "Wrangler"]


def attach(field, path):
    with open(path, "rb") as fh:
        field.save(path.name, File(fh), save=False)


class Command(BaseCommand):
    help = "Seed the StepUp catalogue from the supplied design images."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Delete existing catalogue data first.")

    @transaction.atomic
    def handle(self, *args, **options):
        if options["reset"]:
            Banner.objects.all().delete()
            ProductImage.objects.all().delete()
            ProductVariant.objects.filter(order_items__isnull=True).delete()
            Product.objects.filter(order_items__isnull=True).delete()
            self.stdout.write("Catalogue cleared (products that appear in orders were kept).")

        rng = random.Random(2026)
        colors = {n: Color.objects.get_or_create(name=n, defaults={"hex_code": h})[0] for n, h in COLORS.items()}
        styles = {}
        for i, s in enumerate(STYLES):
            styles[s], _ = Style.objects.get_or_create(name=s, defaults={"display_order": i})

        cats = {}
        for name, slug, desc, img, order in CATEGORIES:
            cat, created = Category.objects.get_or_create(slug=slug, defaults={"name": name, "description": desc,
                                                                             "display_order": order})
            if created or not cat.image:
                attach(cat.image, ASSETS / "categories" / img)
                cat.save()
            cats[slug] = cat

        for b in EXTRA_BRANDS:
            Brand.objects.get_or_create(name=b)

        created_count = 0
        for idx, (file, cat, brand, name, style, price, rating, cols, trending, discount) in enumerate(PRODUCTS):
            if Product.objects.filter(name=name).exists():
                continue
            brand_obj = Brand.objects.get_or_create(name=brand)[0] if brand else None
            desc = DESCRIPTIONS.get(name) or (
                f"{name} from {brand or 'StepUp'} — {STYLE_COPY.get(style, 'made for comfort and style')}. "
                "Easy to style, built to last, and backed by our 7-day easy return & exchange."
            )
            product = Product(category=cats[cat], brand=brand_obj, style=styles[style], name=name,
                              description=desc, price=Decimal(price),
                              discount_price=Decimal(discount) if discount else None,
                              rating=Decimal(rating), rating_count=rng.randint(4, 40), is_trending=trending)
            attach(product.image, ASSETS / "products" / file)
            product.save()
            # Stagger creation time so "New Arrivals" sort is meaningful.
            Product.objects.filter(pk=product.pk).update(
                created_at=product.created_at.replace(microsecond=0) - __import__("datetime").timedelta(hours=idx)
            )
            for c in cols:
                for size in SIZES[cat]:
                    stock = rng.choice([0, 3, 5, 8, 10, 12, 15, 20]) if size not in ("41", "38", "30") else 15
                    ProductVariant.objects.create(product=product, color=colors[c], size=size, stock=stock)
            created_count += 1

        # Product-detail gallery for the Harlan boat shoe (supplied gallery images).
        harlan = Product.objects.filter(name="Harlan Mens Tan Boat Shoe").first()
        if harlan and not harlan.images.exists():
            for order, f in enumerate(["harlan-front.png", "harlan-back.png", "harlan-side.png",
                                       "harlan-closeup.png", "harlan-lifestyle.png"]):
                img = ProductImage(product=harlan, alt_text=f"Harlan boat shoe {f.split('-')[1].split('.')[0]} view",
                                   display_order=order)
                attach(img.image, ASSETS / "gallery" / f)
                img.save()

        if not Banner.objects.exists():
            for order, (title, file, link) in enumerate(BANNERS):
                banner = Banner(title=title, link=link, display_order=order)
                attach(banner.image, ASSETS / "banners" / file)
                banner.save()

        # Restore missing image files for existing database records.
        for name, slug, desc, img, order in CATEGORIES:
            category = cats[slug]
            if not category.image or not category.image.storage.exists(category.image.name):
                attach(category.image, ASSETS / "categories" / img)
                category.save(update_fields=["image"])

        for file, cat, brand, name, style, price, rating, cols, trending, discount in PRODUCTS:
            product = Product.objects.filter(name=name).first()
            if product and (
                not product.image
                or not product.image.storage.exists(product.image.name)
            ):
                attach(product.image, ASSETS / "products" / file)
                product.save(update_fields=["image"])

        for order, (title, file, link) in enumerate(BANNERS):
            banner = Banner.objects.filter(title=title).first()
            if banner and (
                not banner.image
                or not banner.image.storage.exists(banner.image.name)
            ):
                attach(banner.image, ASSETS / "banners" / file)
                banner.save(update_fields=["image"])

        # Restore missing product gallery files without deleting existing records.
        if harlan:
            gallery_files = [
                "harlan-front.png", "harlan-back.png", "harlan-side.png",
                "harlan-closeup.png", "harlan-lifestyle.png",
            ]
            for order, filename in enumerate(gallery_files):
                gallery_image = harlan.images.filter(display_order=order).first()
                if gallery_image and (
                    not gallery_image.image
                    or not gallery_image.image.storage.exists(gallery_image.image.name)
                ):
                    attach(gallery_image.image, ASSETS / "gallery" / filename)
                    gallery_image.save(update_fields=["image"])

        self.stdout.write(self.style.SUCCESS(
            f"Seed complete: {created_count} new products, {Product.objects.count()} total, "
            f"{ProductVariant.objects.count()} variants, {Banner.objects.count()} banners."
        ))