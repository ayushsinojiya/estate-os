"""Synthetic, hand-labeled benchmark. No customer documents or generated aliases.

All original facts below are synthetic English canonical facts. Queries include
native scripts and colloquial Romanized variants, intentionally without aliases
in the documents. Labels identify properties, not arbitrary source chunks.
"""

# id, identity/core, amenities, connectivity
PROPERTIES = [
    ("p01", "Shivalik Sky | Type A | South Bopal, Ahmedabad | 3 BHK apartment | carpet area 1250 sqft | INR 9200000 (92 lakh) | ready to move", "swimming pool, gym, EV charging, two covered parking spaces", "DPS Bopal school 700 m; SP Ring Road 1 km"),
    ("p02", "Shivalik Sky | Type B | South Bopal, Ahmedabad | 3 BHK apartment | carpet area 1250 sqft | INR 9800000 (98 lakh) | ready to move | private foyer 85 sqft", "gym, swimming pool, one covered parking space", "DPS Bopal school 700 m"),
    ("p03", "Riverstone Heights | Paldi, Ahmedabad | 2 BHK apartment | carpet area 850 sqft | INR 6200000 (62 lakh) | possession December 2027", "rooftop garden, children's play area", "Paldi metro station 500 m"),
    ("p04", "Lotus Residency | Wakad, Pune | 2 BHK apartment | carpet area 780 sqft | INR 6800000 (68 lakh) | ready to move", "gym, swimming pool, children's play area", "Hinjewadi IT Park 4 km"),
    ("p05", "Sahyadri Gardens | Baner, Pune | 3 BHK apartment | carpet area 1100 sqft | INR 11500000 (1.15 crore) | possession June 2028", "tennis court, jogging track, clubhouse", "Balewadi High Street 2 km"),
    ("p06", "Independent resale apartment | Kothrud, Pune | 2 BHK | carpet area 720 sqft | INR 7500000 (75 lakh) | ready to move | furnished", "lift, one covered parking space", "Vanaz metro station 300 m"),
    ("p07", "Sea Breeze | Andheri West, Mumbai | 1 BHK apartment | carpet area 450 sqft | INR 11000000 (1.1 crore) | ready to move", "lift, security", "Versova metro station 800 m"),
    ("p08", "Palm Court | Thane, Mumbai | 2 BHK apartment | carpet area 700 sqft | INR 9500000 (95 lakh) | possession March 2027", "swimming pool, badminton court, gym", "Viviana Mall 1 km"),
    ("p09", "Green Acre Villa | Shela, Ahmedabad | 4 BHK villa | plot area 2400 sqft | built-up area 2800 sqft | INR 24000000 (2.4 crore) | ready to move", "private garden, two parking spaces, solar panels", "Shanti Asiatic School 1.5 km"),
    ("p10", "Aarav Commercial | SG Highway, Ahmedabad | office | built-up area 1200 sqft | INR 8500000 (85 lakh) | ready to move", "conference room, visitor parking, power backup", "Gota junction 500 m"),
    ("p11", "Narmada Enclave | Adajan, Surat | 3 BHK apartment | carpet area 1050 sqft | INR 7800000 (78 lakh) | ready to move", "gym, senior citizen seating, children's play area", "Tapi riverfront 900 m"),
    ("p12", "Veda Homes | Hinjewadi, Pune | studio apartment | carpet area 350 sqft | INR 3200000 (32 lakh) | possession December 2026", "coworking lounge, laundry room", "Rajiv Gandhi Infotech Park 1 km"),
    ("p13", "Shivalik Park | Maninagar, Ahmedabad | 2 BHK apartment | carpet area 900 sqft | INR 5800000 (58 lakh) | ready to move", "garden, lift, security", "Kankaria Lake 1 km"),
    ("p14", "Lotus Heights | Vastral, Ahmedabad | 2 BHK apartment | carpet area 780 sqft | INR 4800000 (48 lakh) | possession June 2027", "gym, garden", "Vastral metro station 600 m"),
    ("p15", "Riverstone View | Baner, Pune | 3 BHK apartment | carpet area 1250 sqft | INR 13500000 (1.35 crore) | ready to move", "gym, swimming pool, library", "Baner Road 500 m"),
    ("p16", "Independent resale row house | Naranpura, Ahmedabad | 3 BHK | built-up area 1650 sqft | INR 9200000 (92 lakh) | ready to move | two balconies", "one parking space", "Sardar Patel Stadium 2 km"),
]

# Each group deliberately covers varied names, locations, BHK, price, area,
# amenities, configuration distinctions, and possession. A modest diagnostic,
# not a held-out market-wide evaluation or an exact-filter test.
QUERY_GROUPS = {
    "en": [
        ("Shivalik Sky Type B 3 BHK with private foyer", "p02"),
        ("2 BHK in Wakad under 70 lakh with pool", "p04"),
        ("Shela four bedroom villa with solar panels and private garden", "p09"),
        ("Office on SG Highway 1200 square feet at 85 lakh", "p10"),
        ("Paldi 2 BHK 850 sqft possession December 2027", "p03"),
    ],
    "hi": [
        ("साउथ बोपल में 92 लाख का तीन बीएचके जिसमें ईवी चार्जिंग है", "p01"),
        ("वाकड पुणे में 68 लाख का दो बेडरूम घर और स्विमिंग पूल", "p04"),
        ("शेला में चार बेडरूम का विला निजी बगीचे के साथ", "p09"),
        ("अंधेरी वेस्ट में एक बीएचके तैयार फ्लैट", "p07"),
        ("पालडी में मेट्रो के पास दो बीएचके 62 लाख", "p03"),
    ],
    "mr": [
        ("कोथरूडमध्ये फर्निश्ड दोन बेडरूमचा तयार फ्लॅट हवा", "p06"),
        ("बाणेरमध्ये टेनिस कोर्ट असलेला तीन बीएचके प्रकल्प", "p05"),
        ("हिंजवडीमध्ये 32 लाखांचा स्टुडिओ फ्लॅट", "p12"),
        ("वाकडमध्ये 780 चौरस फूट कार्पेट क्षेत्राचा दोन बीएचके फ्लॅट", "p04"),
        ("ठाण्यात बॅडमिंटन कोर्ट आणि स्विमिंग पूल असलेले घर", "p08"),
    ],
    "gu": [
        ("સાઉથ બોપલમાં ત્રણ બેડરૂમનું 92 લાખનું તૈયાર ઘર", "p01"),
        ("શેલામાં ખાનગી બગીચાવાળો ચાર બેડરૂમનો વિલા", "p09"),
        ("પાલડીમાં મેટ્રો નજીક બે બીએચકે 62 લાખમાં", "p03"),
        ("સુરત અડાજણમાં ત્રણ બેડરૂમનું 78 લાખનું ઘર", "p11"),
        ("મણિનગરમાં કાંકરિયા તળાવ નજીક બે બીએચકે", "p13"),
    ],
    "romanized_hi": [
        ("South Bopal mein 3 bhk 92 lakh ka ghar EV charging ke saath", "p01"),
        ("Andheri West mein ek bedroom ready flat chahiye", "p07"),
        ("Shela mein char bedroom villa apne garden ke saath", "p09"),
        ("Paldi mein metro ke paas 62 lakh ka do bhk", "p03"),
        ("Shivalik Sky Type B mein private foyer kitna hai", "p02"),
    ],
    "romanized_mr": [
        ("Kothrud madhye furnished don bedroom cha tayar flat pahije", "p06"),
        ("Baner madhye tennis court aslela teen bhk ghar", "p05"),
        ("Hinjewadi madhye 32 lakh cha studio flat hava", "p12"),
        ("Wakad madhye 780 square foot carpet don bhk ghar", "p04"),
        ("Thane madhye badminton court ani swimming pool aslela flat", "p08"),
    ],
    "romanized_gu": [
        ("South Bopal ma tran bedroom nu 92 lakh nu taiyar ghar", "p01"),
        ("Shela ma char bedroom no villa khangi bagicha sathe", "p09"),
        ("Paldi ma metro pase be bhk 62 lakh ma joie", "p03"),
        ("Adajan Surat ma tran bedroom nu 78 lakh nu ghar", "p11"),
        ("Maninagar ma Kankaria talav pase be bedroom nu ghar", "p13"),
    ],
    "mixed": [
        ("Shivalik Sky Type A में EV charging અને gym છે?", "p01"),
        ("Baner मध्ये 3 BHK tennis court possession June 2028", "p05"),
        ("SG Highway પર office 1200 sqft 85 lakh", "p10"),
        ("Naranpura 3 BHK બે balconies ready to move 92 lakh", "p16"),
        ("Vastral में Lotus Heights 2 BHK 48 lakh", "p14"),
    ],
}


def corpus(property_count=1000):
    if property_count < len(PROPERTIES):
        raise ValueError("property_count must include all labeled properties")
    result = []
    for entity_id, core, amenities, location in PROPERTIES:
        identity = " | ".join(core.split(" | ")[:3])
        for section, text in (("PROPERTY_CORE", core), ("AMENITIES", identity + " | Amenities: " + amenities), ("LOCATION_CONNECTIVITY", identity + " | Nearby: " + location)):
            result.append({"entity_id": entity_id, "section_type": section, "content": text})
    localities = ["Bodakdev, Ahmedabad", "Vesu, Surat", "Kharadi, Pune", "Powai, Mumbai", "Satellite, Ahmedabad", "Hadapsar, Pune", "Dombivli, Mumbai", "Chandkheda, Ahmedabad"]
    amenity_sets = ["gym, lift", "garden, security", "swimming pool, clubhouse", "children's play area, parking"]
    for i in range(property_count - len(PROPERTIES)):
        entity_id = f"d{i:04d}"
        identity = f"Synthetic Residence {i + 1:04d} | {localities[i % len(localities)]} | {1 + i % 4} BHK apartment"
        # These are distinct, deterministic synthetic properties for scale timing.
        core = identity + f" | carpet area {500 + (i * 37) % 1400} sqft | INR {4000000 + (i * 17311) % 15000000} | possession December {2027 + i % 3}"
        result.append({"entity_id": entity_id, "section_type": "PROPERTY_CORE", "content": core})
        result.append({"entity_id": entity_id, "section_type": "AMENITIES", "content": identity + " | Amenities: " + amenity_sets[i % 4]})
    return result


def queries():
    return [{"id": f"{language}-{i+1}", "language": language, "text": text, "relevant": [target]}
            for language, cases in QUERY_GROUPS.items() for i, (text, target) in enumerate(cases)]
