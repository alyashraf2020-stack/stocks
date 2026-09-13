import json

equities = [
    # Banks (البنوك)
    {"ticker": "COMI", "arabic_name": "البنك التجاري الدولي - مصر", "english_name": "Commercial International Bank (Egypt)", "isin": "EGS60121C018", "sector": "البنوك", "listing_status": "ACTIVE", "indices": ["EGX30", "EGX100"]},
    {"ticker": "ADIB", "arabic_name": "مصرف أبوظبي الإسلامي - مصر", "english_name": "Abu Dhabi Islamic Bank - Egypt", "isin": "EGS60331C017", "sector": "البنوك", "listing_status": "ACTIVE", "indices": ["EGX30", "EGX100"]},
    {"ticker": "CIEB", "arabic_name": "بنك كريدي أجريكول مصر", "english_name": "Credit Agricole Egypt", "isin": "EGS60081C014", "sector": "البنوك", "listing_status": "ACTIVE", "indices": ["EGX30", "EGX100"]},
    {"ticker": "HDBK", "arabic_name": "بنك التعمير والإسكان", "english_name": "Housing & Development Bank", "isin": "EGS60141C016", "sector": "البنوك", "listing_status": "ACTIVE", "indices": ["EGX30", "EGX100"]},
    {"ticker": "QNBA", "arabic_name": "بنك قطر الوطني الأهلي", "english_name": "Qatar National Bank Alahli", "isin": "EGS60041C018", "sector": "البنوك", "listing_status": "ACTIVE", "indices": ["EGX30", "EGX100"]},
    {"ticker": "SAUD", "arabic_name": "بنك البركة مصر", "english_name": "Al Baraka Bank Egypt", "isin": "EGS60011C011", "sector": "البنوك", "listing_status": "ACTIVE", "indices": ["EGX70", "EGX100"]},
    {"ticker": "FAIT", "arabic_name": "بنك فيصل الإسلامي المصري - بالجنيه", "english_name": "Faisal Islamic Bank of Egypt - EGP", "isin": "EGS60031C019", "sector": "البنوك", "listing_status": "ACTIVE", "indices": ["EGX70", "EGX100"]},
    {"ticker": "FAID", "arabic_name": "بنك فيصل الإسلامي المصري - بالدولار", "english_name": "Faisal Islamic Bank of Egypt - USD", "isin": "EGS60032C018", "sector": "البنوك", "listing_status": "ACTIVE", "indices": []},
    {"ticker": "EGBE", "arabic_name": "البنك المصري الخليجي", "english_name": "Egyptian Gulf Bank", "isin": "EGS60061C016", "sector": "البنوك", "listing_status": "ACTIVE", "indices": ["EGX70", "EGX100"]},
    {"ticker": "EXPA", "arabic_name": "بنك تنمية الصادرات", "english_name": "Export Development Bank of Egypt", "isin": "EGS60101C010", "sector": "البنوك", "listing_status": "ACTIVE", "indices": ["EGX70", "EGX100"]},
    {"ticker": "CANA", "arabic_name": "بنك قناة السويس", "english_name": "Suez Canal Bank", "isin": "EGS60071C015", "sector": "البنوك", "listing_status": "ACTIVE", "indices": ["EGX70", "EGX100"]},

    # Basic Resources & Petrochemicals (الموارد الأساسية والكيماويات)
    {"ticker": "ABUK", "arabic_name": "أبو قير للأسمدة والصناعات الكيماوية", "english_name": "Abu Qir Fertilizers and Chemicals", "isin": "EGS38191C010", "sector": "الموارد الأساسية", "listing_status": "ACTIVE", "indices": ["EGX30", "EGX100"]},
    {"ticker": "MFPC", "arabic_name": "مصر لإنتاج الأسمدة - موبكو", "english_name": "Misr Fertilizers Production Company - MOPCO", "isin": "EGS380S1C017", "sector": "الموارد الأساسية", "listing_status": "ACTIVE", "indices": ["EGX30", "EGX100"]},
    {"ticker": "ESRS", "arabic_name": "حديد عز", "english_name": "Ezz Steel", "isin": "EGS33041C012", "sector": "الموارد الأساسية", "listing_status": "ACTIVE", "indices": ["EGX30", "EGX100"]},
    {"ticker": "AMOC", "arabic_name": "الإسكندرية للزيوت المعدنية - أموك", "english_name": "Alexandria Mineral Oils Company - AMOC", "isin": "EGS380P1C010", "sector": "الموارد الأساسية", "listing_status": "ACTIVE", "indices": ["EGX30", "EGX100"]},
    {"ticker": "SKPC", "arabic_name": "سيدي كرير للبتروكيماويات - سيدبك", "english_name": "Sidi Kerir Petrochemicals - SIDPEC", "isin": "EGS380B1C010", "sector": "الموارد الأساسية", "listing_status": "ACTIVE", "indices": ["EGX30", "EGX100"]},
    {"ticker": "EGCH", "arabic_name": "الصناعات الكيماوية المصرية - كيما", "english_name": "Egyptian Chemical Industries - KIMA", "isin": "EGS38201C017", "sector": "الموارد الأساسية", "listing_status": "ACTIVE", "indices": ["EGX70", "EGX100"]},
    {"ticker": "IRON", "arabic_name": "الحديد والصلب المصرية", "english_name": "Egyptian Iron & Steel", "isin": "EGS33011C015", "sector": "الموارد الأساسية", "listing_status": "SUSPENDED", "indices": []},
    {"ticker": "MISR", "arabic_name": "مصر للأسمنت - قنا", "english_name": "Misr Cement - Qena", "isin": "EGS3C341C012", "sector": "الموارد الأساسية", "listing_status": "ACTIVE", "indices": ["EGX70", "EGX100"]},
    {"ticker": "KWIN", "arabic_name": "كفر الزيات للمبيدات والكيماويات", "english_name": "Kafr El Zayat Pesticides", "isin": "EGS38051C017", "sector": "الموارد الأساسية", "listing_status": "ACTIVE", "indices": ["EGX70"]},
    {"ticker": "PACH", "arabic_name": "البويات والصناعات الكيماوية - باكين", "english_name": "Paints & Chemical Industries - Pachin", "isin": "EGS38161C013", "sector": "الموارد الأساسية", "listing_status": "ACTIVE", "indices": []},
    {"ticker": "MICH", "arabic_name": "مصر لصناعة الكيماويات", "english_name": "Misr Chemical Industries", "isin": "EGS38031C019", "sector": "الموارد الأساسية", "listing_status": "ACTIVE", "indices": ["EGX70", "EGX100"]},

    # Real Estate & Construction (العقارات والإنشاءات)
    {"ticker": "TMGH", "arabic_name": "مجموعة طلعت مصطفى القابضة", "english_name": "Talaat Moustafa Group Holding", "isin": "EGS691S1C011", "sector": "العقارات", "listing_status": "ACTIVE", "indices": ["EGX30", "EGX100"]},
    {"ticker": "OCDI", "arabic_name": "السادس من أكتوبر للتنمية والاستثمار - سوديك", "english_name": "Sixth of October Development & Investment (SODIC)", "isin": "EGS65591C017", "sector": "العقارات", "listing_status": "ACTIVE", "indices": ["EGX30", "EGX100"]},
    {"ticker": "PHDC", "arabic_name": "بالم هيلز للتعمير", "english_name": "Palm Hills Developments", "isin": "EGS691A1C011", "sector": "العقارات", "listing_status": "ACTIVE", "indices": ["EGX30", "EGX100"]},
    {"ticker": "MASR", "arabic_name": "مدينة مصر للإسكان والتعمير", "english_name": "Madinet Masr for Housing and Development", "isin": "EGS65031C010", "sector": "العقارات", "listing_status": "ACTIVE", "indices": ["EGX30", "EGX100"]},
    {"ticker": "HELI", "arabic_name": "مصر الجديدة للإسكان والتعمير", "english_name": "Heliopolis Company for Housing & Development", "isin": "EGS65011C012", "sector": "العقارات", "listing_status": "ACTIVE", "indices": ["EGX30", "EGX100"]},
    {"ticker": "EMFD", "arabic_name": "إعمار مصر للتنمية", "english_name": "Emaar Misr for Development", "isin": "EGS693V1C014", "sector": "العقارات", "listing_status": "ACTIVE", "indices": ["EGX30", "EGX100"]},
    {"ticker": "ORHD", "arabic_name": "أوراسكوم للتنمية مصر", "english_name": "Orascom Development Egypt", "isin": "EGS69081C013", "sector": "العقارات", "listing_status": "ACTIVE", "indices": ["EGX30", "EGX100"]},
    {"ticker": "ORAS", "arabic_name": "أوراسكوم كونستراكشون بي إل سي", "english_name": "Orascom Construction PLC", "isin": "EGS95001C011", "sector": "الإنشاءات ومواد البناء", "listing_status": "ACTIVE", "indices": ["EGX30", "EGX100"]},
    {"ticker": "ACRO", "arabic_name": "أكرو مصر للشدات والسقالات المعدنية", "english_name": "Acro Misr for Metallic Scaffolding", "isin": "EGS32051C013", "sector": "الإنشاءات ومواد البناء", "listing_status": "ACTIVE", "indices": ["EGX70"]},
    {"ticker": "UNIT", "arabic_name": "المتحدة للإسكان والتعمير", "english_name": "United Housing & Development", "isin": "EGS65081C015", "sector": "العقارات", "listing_status": "ACTIVE", "indices": ["EGX70", "EGX100"]},
    {"ticker": "ELSH", "arabic_name": "الشمس للإسكان والتعمير", "english_name": "El Shams Housing & Urban Development", "isin": "EGS65071C016", "sector": "العقارات", "listing_status": "ACTIVE", "indices": ["EGX70", "EGX100"]},
    {"ticker": "AMER", "arabic_name": "مجموعة عامر القابضة - عامر جروب", "english_name": "Amer Group Holding", "isin": "EGS691B1C010", "sector": "العقارات", "listing_status": "ACTIVE", "indices": ["EGX70"]},
    {"ticker": "PORT", "arabic_name": "بورتو جروب القابضة", "english_name": "Porto Group Holding", "isin": "EGS69411C010", "sector": "العقارات", "listing_status": "ACTIVE", "indices": []},
    {"ticker": "ARAB", "arabic_name": "المطورون العرب القابضة", "english_name": "Arab Developers Holding", "isin": "EGS69401C011", "sector": "العقارات", "listing_status": "ACTIVE", "indices": ["EGX70", "EGX100"]},
    {"ticker": "AIH", "arabic_name": "العربية لإدارة وتطوير الأصول", "english_name": "Arab Co. for Asset Management and Development", "isin": "EGS69491C012", "sector": "العقارات", "listing_status": "ACTIVE", "indices": ["EGX70"]},
    {"ticker": "NCCW", "arabic_name": "النصر للأعمال المدنية", "english_name": "El Nasr Civil Works", "isin": "EGS21081C013", "sector": "الإنشاءات ومواد البناء", "listing_status": "ACTIVE", "indices": ["EGX70"]},
    {"ticker": "AREH", "arabic_name": "المجموعة العربية للتنمية والاستثمار العقاري", "english_name": "Arab Real Estate Development & Investment", "isin": "EGS65541C012", "sector": "العقارات", "listing_status": "ACTIVE", "indices": []},
    {"ticker": "MENA", "arabic_name": "مينا للاستثمار السياحي والعقاري", "english_name": "Mena Touristic & Real Estate Investment", "isin": "EGS65091C014", "sector": "العقارات", "listing_status": "ACTIVE", "indices": []},

    # Financial Services (الخدمات المالية غير المصرفية)
    {"ticker": "HRHO", "arabic_name": "مجموعة إي إف جي القابضة - هيرميس", "english_name": "EFG Holding", "isin": "EGS69101C018", "sector": "الخدمات المالية غير المصرفية", "listing_status": "ACTIVE", "indices": ["EGX30", "EGX100"]},
    {"ticker": "CCAP", "arabic_name": "شركة القلعة للاستشارات المالية", "english_name": "Qalaa Holdings", "isin": "EGS691G1C018", "sector": "الخدمات المالية غير المصرفية", "listing_status": "ACTIVE", "indices": ["EGX30", "EGX100"]},
    {"ticker": "BTFH", "arabic_name": "بلتون القابضة", "english_name": "Beltone Holding", "isin": "EGS691B1C011", "sector": "الخدمات المالية غير المصرفية", "listing_status": "ACTIVE", "indices": ["EGX30", "EGX100"]},
    {"ticker": "BINV", "arabic_name": "بي إنفستمنتس القابضة", "english_name": "B Investments Holding", "isin": "EGS693M1C015", "sector": "الخدمات المالية غير المصرفية", "listing_status": "ACTIVE", "indices": ["EGX70", "EGX100"]},
    {"ticker": "CNFN", "arabic_name": "كونتكت المالية القابضة", "english_name": "Contact Financial Holding", "isin": "EGS69451C012", "sector": "الخدمات المالية غير المصرفية", "listing_status": "ACTIVE", "indices": ["EGX70", "EGX100"]},
    {"ticker": "RAYA", "arabic_name": "راية القابضة للاستثمارات المالية", "english_name": "Raya Holding for Financial Investments", "isin": "EGS69051C016", "sector": "الخدمات المالية غير المصرفية", "listing_status": "ACTIVE", "indices": ["EGX70", "EGX100"]},
    {"ticker": "CICH", "arabic_name": "سي آي كابيتال القابضة للاستثمارات المالية", "english_name": "CI Capital Holding For Financial Investments", "isin": "EGS69411C028", "sector": "الخدمات المالية غير المصرفية", "listing_status": "ACTIVE", "indices": ["EGX70", "EGX100"]},
    {"ticker": "CSAG", "arabic_name": "القاهرة للإسكان والتعمير (استثمارات مالية)", "english_name": "Cairo For Housing and Development", "isin": "EGS65041C019", "sector": "الخدمات المالية غير المصرفية", "listing_status": "ACTIVE", "indices": ["EGX70"]},
    {"ticker": "UNIP", "arabic_name": "العالمية للاستثمار والتنمية", "english_name": "Universal for Financial Investment", "isin": "EGS69131C015", "sector": "الخدمات المالية غير المصرفية", "listing_status": "ACTIVE", "indices": []},
    {"ticker": "SHUAA", "arabic_name": "شعاع للخدمات المالية", "english_name": "Shuaa Capital Egypt", "isin": "EGS69211C019", "sector": "الخدمات المالية غير المصرفية", "listing_status": "ACTIVE", "indices": []},

    # Telecom & Technology (الاتصالات والتكنولوجيا)
    {"ticker": "ETEL", "arabic_name": "الشركة المصرية للاتصالات - وي", "english_name": "Telecom Egypt (WE)", "isin": "EGS48031C016", "sector": "التكنولوجيا والاتصالات", "listing_status": "ACTIVE", "indices": ["EGX30", "EGX100"]},
    {"ticker": "FWRY", "arabic_name": "فوري لتكنولوجيا البنوك والمدفوعات الإلكترونية", "english_name": "Fawry for Banking & Electronic Payment", "isin": "EGS745L1C014", "sector": "التكنولوجيا والاتصالات", "listing_status": "ACTIVE", "indices": ["EGX30", "EGX100"]},
    {"ticker": "RACC", "arabic_name": "راية لخدمات مراكز الاتصالات", "english_name": "Raya Contact Center", "isin": "EGS74261C013", "sector": "التكنولوجيا والاتصالات", "listing_status": "ACTIVE", "indices": ["EGX70"]},
    {"ticker": "VERT", "arabic_name": "فيرتيكا للبرمجيات", "english_name": "Vertika for Software", "isin": "EGS74451C017", "sector": "التكنولوجيا والاتصالات", "listing_status": "ACTIVE", "indices": ["تميز"]},
    {"ticker": "TRMA", "arabic_name": "ترانس ميديا للخدمات الإعلانية", "english_name": "Trans Media Services", "isin": "EGS74151C016", "sector": "التكنولوجيا والاتصالات", "listing_status": "ACTIVE", "indices": []},

    # Healthcare & Pharma (الرعاية الصحية والأدوية)
    {"ticker": "CLHO", "arabic_name": "مستشفى كليوباترا", "english_name": "Cleopatra Hospital Company", "isin": "EGS729E1C014", "sector": "الرعاية الصحية والأدوية", "listing_status": "ACTIVE", "indices": ["EGX30", "EGX100"]},
    {"ticker": "ISPH", "arabic_name": "ابن سينا فارما", "english_name": "Ibnsina Pharma", "isin": "EGS729K1C016", "sector": "الرعاية الصحية والأدوية", "listing_status": "ACTIVE", "indices": ["EGX30", "EGX100"]},
    {"ticker": "RMDA", "arabic_name": "العاشر من رمضان للصناعات الدوائية - راميدا", "english_name": "Rameda (Tenth of Ramadan for Pharma)", "isin": "EGS729N1C013", "sector": "الرعاية الصحية والأدوية", "listing_status": "ACTIVE", "indices": ["EGX70", "EGX100"]},
    {"ticker": "PHAR", "arabic_name": "المصرية الدولية للصناعات الدوائية - إيبيكو", "english_name": "Egyptian International Pharma (EIPICO)", "isin": "EGS72051C017", "sector": "الرعاية الصحية والأدوية", "listing_status": "ACTIVE", "indices": ["EGX70", "EGX100"]},
    {"ticker": "MCRO", "arabic_name": "ماكرو جروب للمستحضرات الطبية", "english_name": "Macro Group Pharmaceuticals", "isin": "EGS72AR1C019", "sector": "الرعاية الصحية والأدوية", "listing_status": "ACTIVE", "indices": ["EGX70"]},
    {"ticker": "AXPH", "arabic_name": "الإسكندرية للأدوية والصناعات الكيماوية", "english_name": "Alexandria Pharmaceuticals", "isin": "EGS72011C011", "sector": "الرعاية الصحية والأدوية", "listing_status": "ACTIVE", "indices": ["EGX70"]},
    {"ticker": "NIPH", "arabic_name": "النيل للأدوية والصناعات الكيماوية", "english_name": "The Nile Company for Pharmaceuticals", "isin": "EGS72021C010", "sector": "الرعاية الصحية والأدوية", "listing_status": "ACTIVE", "indices": []},
    {"ticker": "SPMD", "arabic_name": "سبيد ميديكال", "english_name": "Speed Medical", "isin": "EGS729I1C010", "sector": "الرعاية الصحية والأدوية", "listing_status": "ACTIVE", "indices": ["EGX70"]},
    {"ticker": "BIOC", "arabic_name": "بيوجينكس فارما", "english_name": "Biogenyx Pharma", "isin": "EGS72AV1C011", "sector": "الرعاية الصحية والأدوية", "listing_status": "ACTIVE", "indices": ["تميز"]},
    {"ticker": "ICDH", "arabic_name": "الدولية للصناعات الطبية - إيكمي", "english_name": "International Co for Medical Industries", "isin": "EGS729D1C015", "sector": "الرعاية الصحية والأدوية", "listing_status": "ACTIVE", "indices": ["تميز"]},

    # Food & Beverage (الأغذية والمشروبات)
    {"ticker": "EAST", "arabic_name": "الشركة الشرقية - إيسترن كومباني", "english_name": "Eastern Company", "isin": "EGS37091C013", "sector": "الأغذية والمشروبات", "listing_status": "ACTIVE", "indices": ["EGX30", "EGX100"]},
    {"ticker": "JUFO", "arabic_name": "جهينة للصناعات الغذائية", "english_name": "Juhayna Food Industries", "isin": "EGS30901C010", "sector": "الأغذية والمشروبات", "listing_status": "ACTIVE", "indices": ["EGX30", "EGX100"]},
    {"ticker": "DOMT", "arabic_name": "الصناعات الغذائية العربية - دومتي", "english_name": "Arabian Food Industries (Domty)", "isin": "EGS30961C014", "sector": "الأغذية والمشروبات", "listing_status": "ACTIVE", "indices": ["EGX70", "EGX100"]},
    {"ticker": "EFID", "arabic_name": "إيديتا للصناعات الغذائية", "english_name": "Edita Food Industries", "isin": "EGS30841C018", "sector": "الأغذية والمشروبات", "listing_status": "ACTIVE", "indices": ["EGX30", "EGX100"]},
    {"ticker": "OBUR", "arabic_name": "عبور لاند للصناعات الغذائية", "english_name": "Obour Land For Food Industries", "isin": "EGS30971C013", "sector": "الأغذية والمشروبات", "listing_status": "ACTIVE", "indices": ["EGX70", "EGX100"]},
    {"ticker": "SUGR", "arabic_name": "الدلتا للسكر", "english_name": "Delta Sugar Company", "isin": "EGS30211C015", "sector": "الأغذية والمشروبات", "listing_status": "ACTIVE", "indices": ["EGX70", "EGX100"]},
    {"ticker": "OLFI", "arabic_name": "القاهرة للزيوت والصابون", "english_name": "Cairo Oil & Soap", "isin": "EGS30241C012", "sector": "الأغذية والمشروبات", "listing_status": "ACTIVE", "indices": ["EGX70"]},
    {"ticker": "AJWA", "arabic_name": "أجواء للصناعات الغذائية - مصر", "english_name": "Ajwa for Food Industries Egypt", "isin": "EGS30361C018", "sector": "الأغذية والمشروبات", "listing_status": "ACTIVE", "indices": ["EGX70"]},
    {"ticker": "MPCO", "arabic_name": "المنصورة للدواجن", "english_name": "Mansoura Poultry", "isin": "EGS02111C018", "sector": "الأغذية والمشروبات", "listing_status": "ACTIVE", "indices": ["EGX70"]},
    {"ticker": "CEFM", "arabic_name": "مطاحن ومخابز الإسكندرية", "english_name": "Alexandria Mills & Bakeries", "isin": "EGS30371C017", "sector": "الأغذية والمشروبات", "listing_status": "ACTIVE", "indices": []},
    {"ticker": "EDFM", "arabic_name": "مطاحن شرق الدلتا", "english_name": "East Delta Mills", "isin": "EGS30381C016", "sector": "الأغذية والمشروبات", "listing_status": "ACTIVE", "indices": []},
    {"ticker": "MDFM", "arabic_name": "مطاحن ومخابز شمال القاهرة", "english_name": "North Cairo Flour Mills", "isin": "EGS30401C012", "sector": "الأغذية والمشروبات", "listing_status": "ACTIVE", "indices": []},
    {"ticker": "SNFC", "arabic_name": "الشرقية الوطنية للأمن الغذائي", "english_name": "Sharkia National Food", "isin": "EGS02061C015", "sector": "الأغذية والمشروبات", "listing_status": "ACTIVE", "indices": []},
    {"ticker": "MILS", "arabic_name": "مطاحن ومخابز الإسكندرية - تميز", "english_name": "Alexandria Flour Mills - Tamayuz", "isin": "EGS30371C025", "sector": "الأغذية والمشروبات", "listing_status": "ACTIVE", "indices": ["تميز"]},

    # Industrial Goods & Auto (السلع الصناعية والسيارات)
    {"ticker": "SWDY", "arabic_name": "السويدي إليكتريك", "english_name": "Elsewedy Electric", "isin": "EGS3G0Z1C014", "sector": "خدمات ومنتجات صناعية وسيارات", "listing_status": "ACTIVE", "indices": ["EGX30", "EGX100"]},
    {"ticker": "AUTO", "arabic_name": "جي بي كوربوريشن (غبور أوتو)", "english_name": "GB Corp (Ghabbour Auto)", "isin": "EGS673T1C012", "sector": "خدمات ومنتجات صناعية وسيارات", "listing_status": "ACTIVE", "indices": ["EGX30", "EGX100"]},
    {"ticker": "EKHO", "arabic_name": "الشركة القابضة المصرية الكويتية - بالجنيه", "english_name": "Egypt Kuwait Holding - EGP", "isin": "EGS69041C017", "sector": "خدمات ومنتجات صناعية وسيارات", "listing_status": "ACTIVE", "indices": ["EGX30", "EGX100"]},
    {"ticker": "EKHOA", "arabic_name": "الشركة القابضة المصرية الكويتية - بالدولار", "english_name": "Egypt Kuwait Holding - USD", "isin": "EGS69042C016", "sector": "خدمات ومنتجات صناعية وسيارات", "listing_status": "ACTIVE", "indices": []},
    {"ticker": "MMIT", "arabic_name": "إم إم جروب للصناعة والتجارة العالمية", "english_name": "MM Group for Industry and International Trade", "isin": "EGS673U1C010", "sector": "خدمات ومنتجات صناعية وسيارات", "listing_status": "ACTIVE", "indices": ["EGX70", "EGX100"]},
    {"ticker": "ARCC", "arabic_name": "الأسمنت العربية", "english_name": "Arabian Cement Company", "isin": "EGS3C371C019", "sector": "الإنشاءات ومواد البناء", "listing_status": "ACTIVE", "indices": ["EGX70", "EGX100"]},
    {"ticker": "SVCE", "arabic_name": "جنوب الوادي للأسمنت", "english_name": "South Valley Cement", "isin": "EGS3C351C011", "sector": "الإنشاءات ومواد البناء", "listing_status": "ACTIVE", "indices": ["EGX70"]},
    {"ticker": "SCEM", "arabic_name": "أسمنت سيناء", "english_name": "Sinai Cement", "isin": "EGS3C331C013", "sector": "الإنشاءات ومواد البناء", "listing_status": "ACTIVE", "indices": []},
    {"ticker": "MCQE", "arabic_name": "مصر للإسمنت - قنا", "english_name": "Misr Cement (Qena)", "isin": "EGS3C341C012", "sector": "الإنشاءات ومواد البناء", "listing_status": "ACTIVE", "indices": ["EGX70"]},
    {"ticker": "ECAP", "arabic_name": "العز للسيراميك والبورسلين - الجوهرة", "english_name": "Al Ezz Ceramics & Porcelain (Gemma)", "isin": "EGS3C041C014", "sector": "الإنشاءات ومواد البناء", "listing_status": "ACTIVE", "indices": ["EGX70"]},
    {"ticker": "PRCL", "arabic_name": "العامة لمنتجات الخزف والصيني - شيني", "english_name": "General Company for Ceramic & Porcelain", "isin": "EGS3C051C013", "sector": "الإنشاءات ومواد البناء", "listing_status": "ACTIVE", "indices": []},
    {"ticker": "BIGP", "arabic_name": "بيج تريد للتجارة والاستثمار", "english_name": "Big Trade for Commercial & Investment", "isin": "EGS67181C017", "sector": "خدمات ومنتجات صناعية وسيارات", "listing_status": "ACTIVE", "indices": ["تميز"]},
    {"ticker": "MBEN", "arabic_name": "إم بي للهندسة", "english_name": "MB Engineering", "isin": "EGS3G051C013", "sector": "خدمات ومنتجات صناعية وسيارات", "listing_status": "ACTIVE", "indices": ["تميز"]},

    # Textiles & Durables (المنسوجات والسلع المعمرة)
    {"ticker": "ORWE", "arabic_name": "النساجون الشرقيون للسجاد", "english_name": "Oriental Weavers Carpet", "isin": "EGS34081C017", "sector": "المنسوجات والسلع المعمرة", "listing_status": "ACTIVE", "indices": ["EGX30", "EGX100"]},
    {"ticker": "DSCW", "arabic_name": "دايس للملابس الجاهزة", "english_name": "Dice Sport & Casual Wear", "isin": "EGS34111C013", "sector": "المنسوجات والسلع المعمرة", "listing_status": "ACTIVE", "indices": ["EGX70", "EGX100"]},
    {"ticker": "KABO", "arabic_name": "النصر للملابس والمنسوجات - كابو", "english_name": "El Nasr Clothing & Textiles - KABO", "isin": "EGS34011C014", "sector": "المنسوجات والسلع المعمرة", "listing_status": "ACTIVE", "indices": ["EGX70"]},
    {"ticker": "AFMC", "arabic_name": "الإسكندرية للغزل والنسيج - سبينالكس", "english_name": "Alexandria Spinning & Weaving (Spinalex)", "isin": "EGS34021C013", "sector": "المنسوجات والسلع المعمرة", "listing_status": "ACTIVE", "indices": ["EGX70"]},
    {"ticker": "ACGC", "arabic_name": "العربية لحليج الأقطان", "english_name": "Arab Cotton Ginning", "isin": "EGS34031C012", "sector": "المنسوجات والسلع المعمرة", "listing_status": "ACTIVE", "indices": ["EGX70"]},

    # Shipping, Utilities & Energy (النقل والشحن والمرافق والطاقة)
    {"ticker": "ALCN", "arabic_name": "الإسكندرية لتداول الحاويات والبضائع", "english_name": "Alexandria Container & Cargo Handling", "isin": "EGS42061C016", "sector": "خدمات النقل والشحن", "listing_status": "ACTIVE", "indices": ["EGX30", "EGX100"]},
    {"ticker": "TAQA", "arabic_name": "طاقة عربية", "english_name": "TAQA Arabia", "isin": "EGS48041C015", "sector": "المرافق والطاقة", "listing_status": "ACTIVE", "indices": ["EGX30", "EGX100"]},
    {"ticker": "MOIL", "arabic_name": "الخدمات الملاحية والبترولية - ماريديف", "english_name": "Maridive & Oil Services", "isin": "EGS48011C018", "sector": "خدمات النقل والشحن", "listing_status": "ACTIVE", "indices": ["EGX70", "EGX100"]},
    {"ticker": "ETRS", "arabic_name": "المصرية لخدمات النقل - إيجيترانس", "english_name": "Egyptian Transport & Commercial Services", "isin": "EGS42081C014", "sector": "خدمات النقل والشحن", "listing_status": "ACTIVE", "indices": ["EGX70"]},
    {"ticker": "CERA", "arabic_name": "العامة للصوامع والتخزين", "english_name": "General Silos & Storage", "isin": "EGS42021C010", "sector": "خدمات النقل والشحن", "listing_status": "ACTIVE", "indices": []},

    # Education, Tourism & Media (التعليم والسياحة والإعلام)
    {"ticker": "CIRA", "arabic_name": "القاهرة للاستثمار والتنمية العقارية - سيرا للتعليم", "english_name": "Cairo Investment & Real Estate Development (CIRA)", "isin": "EGS729M1C014", "sector": "الخدمات التعليمية", "listing_status": "ACTIVE", "indices": ["EGX70", "EGX100"]},
    {"ticker": "TALM", "arabic_name": "تعليم لخدمات الإدارة", "english_name": "Taaleem Management Services", "isin": "EGS72AQ1C010", "sector": "الخدمات التعليمية", "listing_status": "ACTIVE", "indices": ["EGX70", "EGX100"]},
    {"ticker": "EGTS", "arabic_name": "المصرية للمنتجعات السياحية", "english_name": "Egyptian Tourism Resorts", "isin": "EGS70421C010", "sector": "السياحة والترفيه", "listing_status": "ACTIVE", "indices": ["EGX70"]},
    {"ticker": "MHOT", "arabic_name": "مصر للفنادق", "english_name": "Misr Hotels", "isin": "EGS70031C013", "sector": "السياحة والترفيه", "listing_status": "ACTIVE", "indices": ["EGX70"]},
    {"ticker": "ROTO", "arabic_name": "رواد السياحة - الرواد", "english_name": "Rowad Tourism (Al Rowad)", "isin": "EGS70431C019", "sector": "السياحة والترفيه", "listing_status": "ACTIVE", "indices": ["EGX70"]},
    {"ticker": "REMCO", "arabic_name": "رمكو لإنشاء القرى السياحية", "english_name": "Remco Touristic Villages Construction", "isin": "EGS70161C018", "sector": "السياحة والترفيه", "listing_status": "ACTIVE", "indices": []},

    # Paper & Packaging (الورق والتعبئة والتغليف)
    {"ticker": "SMPP", "arabic_name": "الشروق الحديثة للطباعة والتغليف", "english_name": "Shorouk Modern Printing & Packaging", "isin": "EGS39021C011", "sector": "الورق ومواد التعبئة والتغليف", "listing_status": "ACTIVE", "indices": []},

    # Tamayuz SME Market (سوق الشركات الصغيرة والمتوسطة - تميز)
    {"ticker": "BSRY", "arabic_name": "بورسعيد للتنمية الزراعية والمقاولات", "english_name": "Port Said Agricultural Development", "isin": "EGS01011C013", "sector": "العقارات", "listing_status": "ACTIVE", "indices": ["تميز"]},
    {"ticker": "UTOP", "arabic_name": "يوتوبيا للاستثمار العقاري والسياحي", "english_name": "Utopia Real Estate and Tourism", "isin": "EGS65601C014", "sector": "العقارات", "listing_status": "ACTIVE", "indices": ["تميز"]}
]

provenance = {
    "source": "The Egyptian Exchange (EGX) Listed Equities Official Registry",
    "source_updated_at": "2026-09-10T14:30:00+02:00"
}

with open("egx-platform/backend/data/egx_equities.json", "w", encoding="utf-8") as f:
    json.dump({"metadata": provenance, "equities": equities}, f, ensure_ascii=False, indent=2)

print(f"Generated egx_equities.json with {len(equities)} equities")