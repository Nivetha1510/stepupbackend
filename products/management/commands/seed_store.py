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