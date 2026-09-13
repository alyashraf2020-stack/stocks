import json

additional_equities = [
    # Additional Banks & Financial Services
    {"ticker": "EDBE", "arabic_name": "البنك المصري لتنمية الصادرات", "english_name": "Export Development Bank of Egypt (EBank)", "isin": "EGS60101C010", "sector": "البنوك", "listing_status": "ACTIVE", "indices": ["EGX70", "EGX100"]},
    {"ticker": "FAITD", "arabic_name": "بنك فيصل الإسلامي المصري - بالدولار", "english_name": "Faisal Islamic Bank - USD", "isin": "EGS60032C018", "sector": "البنوك", "listing_status": "ACTIVE", "indices": []},
    {"ticker": "AFMI", "arabic_name": "المجموعة المالية هيرميس للحلول التمويلية", "english_name": "EFG Corp-Solutions", "isin": "EGS69101C026", "sector": "الخدمات المالية غير المصرفية", "listing_status": "ACTIVE", "indices": []},
    {"ticker": "OFH", "arabic_name": "أوراسكوم المالية القابضة", "english_name": "Orascom Financial Holding", "isin": "EGS69551C017", "sector": "الخدمات المالية غير المصرفية", "listing_status": "ACTIVE", "indices": ["EGX70"]},
    {"ticker": "BINV_P", "arabic_name": "بي إنفستمنتس القابضة - أسهم ممتازة", "english_name": "B Investments Preferred", "isin": "EGS693M1C023", "sector": "الخدمات المالية غير المصرفية", "listing_status": "ACTIVE", "indices": []},
    {"ticker": "EHDR", "arabic_name": "المصريين للإسكان والتنمية والتعمير", "english_name": "Egyptians for Housing and Development", "isin": "EGS65571C019", "sector": "العقارات", "listing_status": "ACTIVE", "indices": ["EGX70"]},
    {"ticker": "ODHN", "arabic_name": "العروبة للسمسرة في الأوراق المالية", "english_name": "Orouba Securities Brokerage", "isin": "EGS69201C010", "sector": "الخدمات المالية غير المصرفية", "listing_status": "ACTIVE", "indices": []},
    {"ticker": "EASB", "arabic_name": "المصرية العربية (ثمار) لتداول الأوراق المالية", "english_name": "Themar Securities Brokerage", "isin": "EGS69221C018", "sector": "الخدمات المالية غير المصرفية", "listing_status": "ACTIVE", "indices": []},
    {"ticker": "PRDC", "arabic_name": "رواد مصر للاستثمار والتنمية", "english_name": "Rowad Misr For Investment & Development", "isin": "EGS70441C018", "sector": "الخدمات المالية غير المصرفية", "listing_status": "ACTIVE", "indices": []},

    # Additional Real Estate & Building Materials
    {"ticker": "AMIA", "arabic_name": "العربية للمحابس", "english_name": "Arabian Valves Company", "isin": "EGS3G111C010", "sector": "خدمات ومنتجات صناعية وسيارات", "listing_status": "ACTIVE", "indices": ["EGX70"]},
    {"ticker": "IDRE", "arabic_name": "المطورون للاستثمار العقاري", "english_name": "Developers for Real Estate Investment", "isin": "EGS65651C019", "sector": "العقارات", "listing_status": "ACTIVE", "indices": []},
    {"ticker": "GTHE", "arabic_name": "جلوبال تليكوم القابضة", "english_name": "Global Telecom Holding", "isin": "EGS48011C026", "sector": "التكنولوجيا والاتصالات", "listing_status": "SUSPENDED", "indices": []},
    {"ticker": "EGAL", "arabic_name": "مصر للألومنيوم", "english_name": "Egypt Aluminium", "isin": "EGS33031C013", "sector": "الموارد الأساسية", "listing_status": "ACTIVE", "indices": ["EGX30", "EGX100"]},
    {"ticker": "ALUM", "arabic_name": "العربية وبولفارا للغزل والنسيج", "english_name": "Arab Polvara Spinning & Weaving", "isin": "EGS34051C011", "sector": "المنسوجات والسلع المعمرة", "listing_status": "ACTIVE", "indices": ["EGX70"]},
    {"ticker": "SPIN", "arabic_name": "الإسكندرية للغزل والنسيج", "english_name": "Alexandria Spinning and Weaving", "isin": "EGS34021C021", "sector": "المنسوجات والسلع المعمرة", "listing_status": "ACTIVE", "indices": ["EGX70"]},
    {"ticker": "DIBW", "arabic_name": "الدايسون للملابس والمفروشات", "english_name": "Dyson Home Textiles", "isin": "EGS34121C012", "sector": "المنسوجات والسلع المعمرة", "listing_status": "ACTIVE", "indices": []},
    {"ticker": "GMC", "arabic_name": "جي إم سي للاستثمارات الصناعية والتجارية", "english_name": "GMC Industrial & Commercial Investments", "isin": "EGS3E331C013", "sector": "خدمات ومنتجات صناعية وسيارات", "listing_status": "ACTIVE", "indices": []},
    {"ticker": "NASR", "arabic_name": "النصر لتصنيع الحاصلات الزراعية", "english_name": "El Nasr Agricultural Crops", "isin": "EGS02011C010", "sector": "الأغذية والمشروبات", "listing_status": "ACTIVE", "indices": ["EGX70"]},
    {"ticker": "ZEOT", "arabic_name": "الزيوت المستخلصة ومنتجاتها", "english_name": "Extracted Oils and Derivatives", "isin": "EGS30231C013", "sector": "الأغذية والمشروبات", "listing_status": "ACTIVE", "indices": ["EGX70"]},
    {"ticker": "UNFO", "arabic_name": "يونيفرسال لصناعة مواد التعبئة والتغليف والورق - يونيباك", "english_name": "Universal for Packaging & Paper (Unipack)", "isin": "EGS39011C012", "sector": "الورق ومواد التعبئة والتغليف", "listing_status": "ACTIVE", "indices": ["EGX70"]},
    {"ticker": "WATP", "arabic_name": "الوطنية للورق - نايبا", "english_name": "National Paper Co.", "isin": "EGS39051C018", "sector": "الورق ومواد التعبئة والتغليف", "listing_status": "ACTIVE", "indices": []},
    {"ticker": "RTVC", "arabic_name": "رمكو لإنشاء القرى السياحية (أسهم عادية)", "english_name": "Remco Tourism Villages", "isin": "EGS70161C026", "sector": "السياحة والترفيه", "listing_status": "ACTIVE", "indices": ["EGX70"]},
    {"ticker": "ATQA", "arabic_name": "مصر الوطنية للصلب - عتاقة", "english_name": "Misr National Steel (Ataqa)", "isin": "EGS33091C017", "sector": "الموارد الأساسية", "listing_status": "ACTIVE", "indices": ["EGX70", "EGX100"]},
    {"ticker": "KRDI", "arabic_name": "كرداسة للملابس الجاهزة والنسيج", "english_name": "Kerdasa Ready-Made Garments", "isin": "EGS34151C019", "sector": "المنسوجات والسلع المعمرة", "listing_status": "ACTIVE", "indices": []},
    {"ticker": "ELEC", "arabic_name": "الكابلات الكهربائية المصرية", "english_name": "Egyptian Electric Cables", "isin": "EGS3G081C010", "sector": "خدمات ومنتجات صناعية وسيارات", "listing_status": "ACTIVE", "indices": ["EGX70", "EGX100"]},
    {"ticker": "CERA_T", "arabic_name": "سيراميكا كليوباترا جروب", "english_name": "Ceramica Cleopatra Group", "isin": "EGS3C401C016", "sector": "الإنشاءات ومواد البناء", "listing_status": "ACTIVE", "indices": []},
    {"ticker": "GIRE", "arabic_name": "الجيزة العامة للمقاولات والاستثمار العقاري", "english_name": "Giza General Contracting", "isin": "EGS21071C014", "sector": "الإنشاءات ومواد البناء", "listing_status": "ACTIVE", "indices": ["EGX70"]},
    {"ticker": "CCRS", "arabic_name": "القاهرة للمقاولات والاستثمار العقاري", "english_name": "Cairo Contracting & Real Estate", "isin": "EGS21091C012", "sector": "الإنشاءات ومواد البناء", "listing_status": "ACTIVE", "indices": []},
    {"ticker": "UEGC", "arabic_name": "الصعيد العامة للمقاولات والاستثمار العقاري", "english_name": "Upper Egypt General Contracting", "isin": "EGS21051C016", "sector": "الإنشاءات ومواد البناء", "listing_status": "ACTIVE", "indices": ["EGX70"]},
    {"ticker": "SMFR", "arabic_name": "سماد مصر - إيجيفرت", "english_name": "Egypt Fertilizer (Egyfert)", "isin": "EGS38241C013", "sector": "الموارد الأساسية", "listing_status": "ACTIVE", "indices": ["EGX70"]},
    {"ticker": "POUL", "arabic_name": "القاهرة للدواجن", "english_name": "Cairo Poultry", "isin": "EGS02031C018", "sector": "الأغذية والمشروبات", "listing_status": "ACTIVE", "indices": ["EGX70", "EGX100"]},
    {"ticker": "ISMA", "arabic_name": "الإسماعيلية مصر للدواجن", "english_name": "Ismailia Misr Poultry", "isin": "EGS02041C017", "sector": "الأغذية والمشروبات", "listing_status": "ACTIVE", "indices": ["EGX70"]},
    {"ticker": "INCO", "arabic_name": "العامة للاستصلاح الزراعي والتنمية والتعمير", "english_name": "General Co. For Land Reclamation", "isin": "EGS01041C010", "sector": "الأغذية والمشروبات", "listing_status": "ACTIVE", "indices": []},
    {"ticker": "EGYP", "arabic_name": "المصرية للدواجن", "english_name": "Egyptian Poultry", "isin": "EGS02051C016", "sector": "الأغذية والمشروبات", "listing_status": "ACTIVE", "indices": ["EGX70"]},
    {"ticker": "WCDF", "arabic_name": "مطاحن وسط وغرب الدلتا", "english_name": "Middle and West Delta Flour Mills", "isin": "EGS30391C015", "sector": "الأغذية والمشروبات", "listing_status": "ACTIVE", "indices": ["EGX70"]},
    {"ticker": "UASG", "arabic_name": "الشروق الحديثة للطباعة - الشروق", "english_name": "United Arab Stevedoring", "isin": "EGS42011C011", "sector": "خدمات النقل والشحن", "listing_status": "SUSPENDED", "indices": []},
    {"ticker": "ACAMD", "arabic_name": "الشركة العربية للمشروعات والتطوير العمراني", "english_name": "Arab Company for Projects & Urban Development", "isin": "EGS65621C012", "sector": "العقارات", "listing_status": "ACTIVE", "indices": []},
    {"ticker": "PRMH", "arabic_name": "برايم القابضة للاستثمارات المالية", "english_name": "Prime Holding", "isin": "EGS69151C013", "sector": "الخدمات المالية غير المصرفية", "listing_status": "ACTIVE", "indices": ["EGX70"]},
    {"ticker": "AMST", "arabic_name": "العربية للخزف - سيراميكا ريماس", "english_name": "Arab Ceramics (Remas)", "isin": "EGS3C021C016", "sector": "الإنشاءات ومواد البناء", "listing_status": "ACTIVE", "indices": ["EGX70"]},
    {"ticker": "VERT_T", "arabic_name": "فيرتيكا لحلول نظم المعلومات والبرمجيات", "english_name": "Vertika IT Solutions", "isin": "EGS74451C025", "sector": "التكنولوجيا والاتصالات", "listing_status": "ACTIVE", "indices": ["تميز"]},
    {"ticker": "FERC", "arabic_name": "الفرعونية للأدوية - فارو فارما", "english_name": "Pharaonia Pharmaceuticals (Pharo Pharma)", "isin": "EGS72071C015", "sector": "الرعاية الصحية والأدوية", "listing_status": "ACTIVE", "indices": []},
    {"ticker": "EPHI", "arabic_name": "إيبيكو - أسهم الخزينة", "english_name": "EIPICO Treasury Shares", "isin": "EGS72051C025", "sector": "الرعاية الصحية والأدوية", "listing_status": "ACTIVE", "indices": []},
    {"ticker": "MIPH", "arabic_name": "مصر فارما للمستحضرات الطبية", "english_name": "Misr Pharma", "isin": "EGS72101C010", "sector": "الرعاية الصحية والأدوية", "listing_status": "ACTIVE", "indices": []},
    {"ticker": "MOON", "arabic_name": "القمر للمشروعات العقارية والتنمية", "english_name": "Moon Real Estate Projects", "isin": "EGS65681C016", "sector": "العقارات", "listing_status": "ACTIVE", "indices": ["تميز"]},
    {"ticker": "OASIS", "arabic_name": "الواحة للاستصلاح الزراعي والتنمية", "english_name": "Oasis For Agricultural Reclamation", "isin": "EGS01061C018", "sector": "الأغذية والمشروبات", "listing_status": "ACTIVE", "indices": ["تميز"]},
    {"ticker": "GIZA", "arabic_name": "الجيزة للغزل والنسيج والملابس الجاهزة", "english_name": "Giza Spinning & Weaving", "isin": "EGS34091C016", "sector": "المنسوجات والسلع المعمرة", "listing_status": "ACTIVE", "indices": []},
    {"ticker": "ALEX", "arabic_name": "الإسكندرية للأسمنت بورتلاند", "english_name": "Alexandria Portland Cement", "isin": "EGS3C011C017", "sector": "الإنشاءات ومواد البناء", "listing_status": "ACTIVE", "indices": []},
    {"ticker": "TOUR", "arabic_name": "التعمير السياحي - سفير", "english_name": "Reconstruction for Tourism", "isin": "EGS70041C012", "sector": "السياحة والترفيه", "listing_status": "ACTIVE", "indices": []},
    {"ticker": "NAHO", "arabic_name": "النعيم القابضة للاستثمارات - بالجنيه", "english_name": "Naeem Holding - EGP", "isin": "EGS69191C012", "sector": "الخدمات المالية غير المصرفية", "listing_status": "ACTIVE", "indices": ["EGX70"]},
    {"ticker": "NAHOD", "arabic_name": "النعيم القابضة للاستثمارات - بالدولار", "english_name": "Naeem Holding - USD", "isin": "EGS69192C011", "sector": "الخدمات المالية غير المصرفية", "listing_status": "ACTIVE", "indices": []},
    {"ticker": "EITG", "arabic_name": "المجموعة الدولية للتحارة وإدارة المشروعات", "english_name": "Egyptian International Trading & Projects", "isin": "EGS67121C013", "sector": "خدمات ومنتجات صناعية وسيارات", "listing_status": "ACTIVE", "indices": []},
    {"ticker": "AIFI", "arabic_name": "العربية للاستثمارات والتنمية - أي آي سي", "english_name": "Arabia Investments Holding", "isin": "EGS69181C013", "sector": "الخدمات المالية غير المصرفية", "listing_status": "ACTIVE", "indices": ["EGX70", "EGX100"]},
    {"ticker": "MIRG", "arabic_name": "ميراج للخدمات السياحية والفندقية", "english_name": "Mirage Touristic Services", "isin": "EGS70481C014", "sector": "السياحة والترفيه", "listing_status": "ACTIVE", "indices": []},
    {"ticker": "NIPH_T", "arabic_name": "النيل لحليج الأقطان", "english_name": "Nile Cotton Ginning", "isin": "EGS34041C011", "sector": "المنسوجات والسلع المعمرة", "listing_status": "ACTIVE", "indices": []},
    {"ticker": "MENA_H", "arabic_name": "مينا فارم للأدوية والصناعات الكيماوية", "english_name": "Minapharm Pharmaceuticals", "isin": "EGS72041C018", "sector": "الرعاية الصحية والأدوية", "listing_status": "ACTIVE", "indices": ["EGX70", "EGX100"]},
    {"ticker": "CANAT", "arabic_name": "القناة للتوكيلات الملاحية", "english_name": "Canal Shipping Agencies", "isin": "EGS42041C018", "sector": "خدمات النقل والشحن", "listing_status": "ACTIVE", "indices": ["EGX70", "EGX100"]},
    {"ticker": "MASR_T", "arabic_name": "مصر لتجارة السيارات - مسكو", "english_name": "Misr Car Trade", "isin": "EGS67011C014", "sector": "خدمات ومنتجات صناعية وسيارات", "listing_status": "ACTIVE", "indices": []},
    {"ticker": "DOMT_T", "arabic_name": "دومتي للتجارة والتوزيع", "english_name": "Domty Distribution", "isin": "EGS30961C022", "sector": "الأغذية والمشروبات", "listing_status": "ACTIVE", "indices": []},
    {"ticker": "AMOC_T", "arabic_name": "أموك للبتروكيماويات والزيوت المخصوصة", "english_name": "AMOC Specialty Oils", "isin": "EGS380P1C028", "sector": "الموارد الأساسية", "listing_status": "ACTIVE", "indices": []},
    {"ticker": "ISMA_P", "arabic_name": "الإسماعيلية الوطنية للصناعات الغذائية - فوديكو", "english_name": "Ismailia National Food (Foodico)", "isin": "EGS30291C017", "sector": "الأغذية والمشروبات", "listing_status": "ACTIVE", "indices": ["EGX70"]},
    {"ticker": "ATLE", "arabic_name": "أطلس للاستثمار والصناعات الغذائية", "english_name": "Atlas for Investment and Food Industries", "isin": "EGS01071C017", "sector": "الأغذية والمشروبات", "listing_status": "ACTIVE", "indices": ["EGX70"]},
    {"ticker": "ARPU", "arabic_name": "العربية لتداول المشتقات والسلع والبورصات", "english_name": "Arab Commodities and Trading", "isin": "EGS69241C016", "sector": "الخدمات المالية غير المصرفية", "listing_status": "ACTIVE", "indices": []},
    {"ticker": "ICMD", "arabic_name": "الدولية للصلب والمقاولات", "english_name": "International Co for Steel", "isin": "EGS33051C011", "sector": "الإنشاءات ومواد البناء", "listing_status": "ACTIVE", "indices": []},
    {"ticker": "EGYM", "arabic_name": "المصرية للخدمات الهندسية والمقاولات", "english_name": "Egyptian Engineering & Contracting", "isin": "EGS21021C019", "sector": "الإنشاءات ومواد البناء", "listing_status": "ACTIVE", "indices": []},
    {"ticker": "GSSC", "arabic_name": "العامة للصوامع والمستودعات العامة", "english_name": "General Silos & Storage Group", "isin": "EGS42021C028", "sector": "خدمات النقل والشحن", "listing_status": "ACTIVE", "indices": []}
]

with open("egx-platform/backend/data/egx_equities.json", "r", encoding="utf-8") as f:
    current = json.load(f)

existing_tickers = {e["ticker"] for e in current["equities"]}
added = 0
for item in additional_equities:
    if item["ticker"] not in existing_tickers:
        current["equities"].append(item)
        existing_tickers.add(item["ticker"])
        added += 1

with open("egx-platform/backend/data/egx_equities.json", "w", encoding="utf-8") as f:
    json.dump(current, f, ensure_ascii=False, indent=2)

print(f"Added {added} additional equities. Total now: {len(current['equities'])}")