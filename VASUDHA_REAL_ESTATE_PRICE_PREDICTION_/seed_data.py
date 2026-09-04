"""
Vasudha Real Estate — Data Seeder & Model Trainer
Trains the ML model and populates the SQLite database with rich locality intelligence,
rates, 5-year projections, and historical price series.
"""

import sys
from ml_model import ml_model, HISTORICAL_SERIES, SQYD_TO_SQFT
import database
import backend

# Comprehensive Ahmedabad Locality Intelligence Catalog
LOCALITY_METADATA = [
    # -----------------------------------------------------------------------
    # WEST AHMEDABAD (Premium Growth Belts & High-Tech Corridors)
    # -----------------------------------------------------------------------
    {
        "name": "Bodakdev",
        "zone": "West",
        "tier": "Ultra-Luxury",
        "note": "Ahmedabad's most coveted residential enclave featuring sprawling bungalows, elite gated villas, and corporate headquarters along Judges Bungalow Road.",
        "landmarks": "Judges Bungalow Road, Grand Bhagwati, Pakwan Cross Roads, Ahmedabad One Mall",
        "schools_hospitals": "Zydus Hospital, SAL Hospital, Udgam School, Ahmedabad International School",
        "transit": "Quick access to SG Highway & Drive-In Road; Thaltej Metro Station (1.8 km)",
        "livability_score": 9.6,
        "data_source": "ML-fitted 2026 Valuation"
    },
    {
        "name": "Ambli",
        "zone": "West",
        "tier": "Ultra-Luxury",
        "note": "High-end arterial extension along Ambli-Bopal corridor characterized by luxury high-rise penthouses, corporate offices, and lush green open spaces.",
        "landmarks": "Ambli-Bopal Road, The Capital Commercial Hub, Iskcon Temple vicinity",
        "schools_hospitals": "Sterling Hospital, Marengo CIMS, Delhi Public School (DPS Bopal)",
        "transit": "Direct arterial link to SP Ring Road and SG Highway; BRTS connectivity",
        "livability_score": 9.5,
        "data_source": "ML-fitted 2026 Valuation"
    },
    {
        "name": "Sindhu Bhavan Road",
        "zone": "West",
        "tier": "Ultra-Luxury",
        "note": "Ahmedabad's premier lifestyle and commercial Boulevard with luxury designer boutiques, gourmet dining, grade-A tech parks, and elite penthouse towers.",
        "landmarks": "SBR Boulevard, Taj Skyline, Gotila Garden, Symphony House",
        "schools_hospitals": "Zydus Hospital, KD Hospital (10 min), JG International School",
        "transit": "Direct connectivity from SG Highway to SP Ring Road; Wide 45m arterial corridor",
        "livability_score": 9.7,
        "data_source": "ML-fitted 2026 Valuation"
    },
    {
        "name": "Thaltej",
        "zone": "West",
        "tier": "Premium",
        "note": "Established upscale residential locality with tree-lined avenues, top educational centers, and prime connectivity to SG Highway and Drive-In Road.",
        "landmarks": "Thaltej Cross Roads, Acropolis Mall, Thaltej Lake, Udgam Circle",
        "schools_hospitals": "SAL Hospital, CIMS Hospital, Anand Niketan School, Udgam School",
        "transit": "Thaltej Metro Station (Operational East-West corridor), SG Highway BRTS",
        "livability_score": 9.4,
        "data_source": "Observed multi-year trend (iRealty247 ML-fitted)"
    },
    {
        "name": "Satellite",
        "zone": "West",
        "tier": "Premium",
        "note": "Centrally positioned premium neighborhood around ISRO and Shivranjani, renowned for vibrant markets, family-centric residential apartments, and food streets.",
        "landmarks": "ISRO Space Applications Centre, Shivranjani Crossroads, Jodhpur Gam, Star Bazaar",
        "schools_hospitals": "Shalby Hospital (Krishna Shalby), Chaitanya Hospital, Som-Lalit Institute",
        "transit": "Shivranjani BRTS Hub, 132ft Inner Ring Road, Metro feeding station at Commerce Six",
        "livability_score": 9.3,
        "data_source": "Observed multi-year trend (Benchmark ML-fitted)"
    },
    {
        "name": "SG Highway",
        "zone": "West",
        "tier": "Premium",
        "note": "The economic spine of Ahmedabad connecting Sarkhej to Gandhinagar, housing major IT hubs, auto showrooms, healthcare institutions, and entertainment complexes.",
        "landmarks": "Iskcon Mega Mall, Rajpath Club, YMCA Club, Gota Flyover",
        "schools_hospitals": "KD Hospital, Zydus Hospital, SGVP International School, Nirma University",
        "transit": "8-lane expressway corridor, Ahmedabad-Gandhinagar Metro Phase-2 connection",
        "livability_score": 9.2,
        "data_source": "Observed multi-year trend (Benchmark ML-fitted)"
    },
    {
        "name": "Vastrapur",
        "zone": "West",
        "tier": "Premium",
        "note": "Vibrant residential and cultural hub centered around the scenic Vastrapur Lake and world-class educational institutions like IIM Ahmedabad.",
        "landmarks": "Vastrapur Lake, Ahmedabad One (Alpha One) Mall, IIM Ahmedabad Heritage Campus",
        "schools_hospitals": "Sanjivani Hospital, CIMS Hospital, Riverside School, St. Kabir School",
        "transit": "Direct feeder to 132ft Ring Road, BRTS Vastrapur Station",
        "livability_score": 9.4,
        "data_source": "ML-fitted 2026 Valuation"
    },
    {
        "name": "Prahlad Nagar",
        "zone": "West",
        "tier": "Premium",
        "note": "Modern master-planned commercial and residential sector with upscale retail, corporate business parks, and manicured civic gardens.",
        "landmarks": "Prahlad Nagar Garden, Titanium City Center, Corporate Road, AUDA Garden",
        "schools_hospitals": "Shalby Multi-speciality Hospital, Anand Niketan Satellite, DAV International",
        "transit": "Direct connection to 100ft Anandnagar Road, SG Highway, and Makarba",
        "livability_score": 9.3,
        "data_source": "ML-fitted 2026 Valuation"
    },
    {
        "name": "Shela",
        "zone": "West",
        "tier": "Mid-Premium",
        "note": "Rapidly appreciating residential growth hotspot known for high-rise gated communities, clubhouses, wide planned layout, and easy access to Applewoods.",
        "landmarks": "Club O7, Applewoods Township, Shela Lake Development, SP Ring Road Junction",
        "schools_hospitals": "Krishna Shalby Hospital, Shanti Asiatic School, Cosmos Castle School",
        "transit": "Direct linkage onto Sardar Patel Ring Road, 10 min drive to SBR & SG Highway",
        "livability_score": 9.0,
        "data_source": "Observed multi-year trend (iRealty247 ML-fitted)"
    },
    {
        "name": "South Bopal",
        "zone": "West",
        "tier": "Mid-Premium",
        "note": "Cosmopolitan suburban residential neighborhood favored by young professionals, offering modern gated townships, retail hubs, and fitness arenas.",
        "landmarks": "SOBO Center, Gala Gymnasium, Bopal-Ghuma Flyover, Orchid Whitefield",
        "schools_hospitals": "Mamta Hospital, Adwait Multispeciality, Tulip International School",
        "transit": "Connected via SP Ring Road, Bopal BRTS, and planned Metro extension feeder",
        "livability_score": 8.9,
        "data_source": "Observed multi-year trend (Benchmark ML-fitted)"
    },
    {
        "name": "Bopal",
        "zone": "West",
        "tier": "Mid",
        "note": "Well-settled residential suburb with established markets, extensive residential apartment clusters, and self-contained community facilities.",
        "landmarks": "TRP Mall, Bopal Lake, Kabir Enclave, Sterling City",
        "schools_hospitals": "DPS Bopal, Shivam Hospital, Saraswati Vidyamandir",
        "transit": "Bopal BRTS terminal, SP Ring Road arterial access",
        "livability_score": 8.7,
        "data_source": "ML-fitted 2026 Valuation"
    },
    {
        "name": "Science City",
        "zone": "West",
        "tier": "Mid-Premium",
        "note": "High-growth residential belt adjacent to Gujarat Science City park, featuring modern high-rises, wide avenues, and clean urban planning.",
        "landmarks": "Gujarat Science City, Aquatic Gallery, Robotics Gallery, CIMS Hospital Junction",
        "schools_hospitals": "Marengo CIMS Hospital, H.B. Kapadia New High School, Shanti Junior",
        "transit": "Science City Road connecting to SG Highway & SP Ring Road; Metro feeder buses",
        "livability_score": 9.1,
        "data_source": "ML-fitted 2026 Valuation"
    },
    {
        "name": "Shilaj",
        "zone": "West",
        "tier": "Mid-Premium",
        "note": "Peaceful western suburb expanding rapidly into premium gated villa communities and low-density residential towers near Shilaj Lake.",
        "landmarks": "Shilaj Circle, Shilaj Lake, Bopal-Shilaj Main Road",
        "schools_hospitals": "Global Indian International School (GIIS), Lifeline Multispeciality Hospital",
        "transit": "Direct access to SP Ring Road and Science City extension",
        "livability_score": 8.8,
        "data_source": "ML-fitted 2026 Valuation"
    },

    # -----------------------------------------------------------------------
    # NORTH & CENTRAL AHMEDABAD (GIFT City Corridor, Transit Nodes & Heritage)
    # -----------------------------------------------------------------------
    {
        "name": "Motera",
        "zone": "Central",
        "tier": "Mid-Premium",
        "note": "World-famous sports and residential hub anchored by Narendra Modi Stadium, enjoying massive infrastructure investments and direct GIFT City access.",
        "landmarks": "Narendra Modi Cricket Stadium, Motera Sabarmati Riverfront Walk, 4D Square Mall",
        "schools_hospitals": "SMS Multispeciality Hospital, Apollo Hospital (Chandkheda), Podar International School",
        "transit": "Motera Stadium Metro Station (North-South Corridor), Sabarmati Bullet Train Terminal (3 km)",
        "livability_score": 9.2,
        "data_source": "ML-fitted 2026 Valuation"
    },
    {
        "name": "Chandkheda",
        "zone": "Central",
        "tier": "Mid",
        "note": "Rapidly urbanizing northern district bordering Gandhinagar, favored by IT professionals and government employees for affordability and GIFT City proximity.",
        "landmarks": "ONGC Complex, Visat Petrol Pump Circle, IIT Gandhinagar access road",
        "schools_hospitals": "Apollo Hospital, Satyamev Hospital, Kendriya Vidyalaya ONGC",
        "transit": "Chandkheda Road Railway Station, BRTS Corridor, SG Highway-Visat Expressway",
        "livability_score": 8.7,
        "data_source": "Observed multi-year trend (Benchmark ML-fitted)"
    },
    {
        "name": "Gota",
        "zone": "Central",
        "tier": "Mid",
        "note": "Thriving northern corridor on SG Highway with dense modern residential complexes, high rental occupancy, and rapid retail development.",
        "landmarks": "Gota Flyover, Vande Mataram Township, Gota High Court Link Road",
        "schools_hospitals": "KD Hospital, Lifeline Multispeciality, Silver Oak University",
        "transit": "Directly on SG Highway, 10 min to Metro Line 2 and SP Ring Road",
        "livability_score": 8.6,
        "data_source": "Observed multi-year trend (Benchmark ML-fitted)"
    },
    {
        "name": "Vaishnodevi",
        "zone": "North-West",
        "tier": "Mid-Premium",
        "note": "Rapidly appreciating luxury corridor connecting SG Highway and SP Ring Road, popular for high-rise gated townships near Nirma University and Gandhinagar highway.",
        "landmarks": "Vaishnodevi Temple, Nirma University, SG Highway Ring Road Circle, Adani Shantigram (adjacent)",
        "schools_hospitals": "KD Hospital, Apollo Hospital, Nirma Vidyavihar, SGVP International School",
        "transit": "Direct junction of SG Highway & SP Ring Road; Metro Phase-2 Corridor connection",
        "livability_score": 9.3,
        "data_source": "Observed multi-year trend (Benchmark ML-fitted)"
    },
    {
        "name": "Jagatpur",
        "zone": "North-West",
        "tier": "Mid",
        "note": "Flourishing residential hotspot adjoining Godrej Garden City, featuring expansive modern high-rise apartments, greenery, and wide civic infrastructure.",
        "landmarks": "Godrej Garden City, Jagatpur Gota Canal Road, Vande Mataram Prime, New SG Highway",
        "schools_hospitals": "Global Indian International School (GIIS), KD Hospital (5 min), Silver Oak College",
        "transit": "Connected to SG Highway, Chandkheda Visat Road, and SP Ring Road",
        "livability_score": 8.9,
        "data_source": "Observed multi-year trend (Benchmark ML-fitted)"
    },
    {
        "name": "Tragad",
        "zone": "North-West",
        "tier": "Mid",
        "note": "Emerging northern suburban hub offering well-planned residential societies with affordable high-rise living near IOC Road and Chandkheda extension.",
        "landmarks": "Tragad Lake, IOC Road Junction, Satyamev Vista, Tragad Cross Roads",
        "schools_hospitals": "Apollo Hospital (Chandkheda), Satyamev Multispeciality, Podar International",
        "transit": "IOC Road connecting directly to SG Highway and Chandkheda Visat Circle",
        "livability_score": 8.7,
        "data_source": "Observed multi-year trend (Benchmark ML-fitted)"
    },
    {
        "name": "Zundal",
        "zone": "North",
        "tier": "Mid-Premium",
        "note": "Strategic twin-city growth corridor between Ahmedabad and Gandhinagar on SP Ring Road, famous for rapid development and clean surroundings.",
        "landmarks": "Zundal Circle, SP Ring Road North, Gandhinagar Twin-City Highway, Vaishnodevi extension",
        "schools_hospitals": "Apollo Hospital, SMS Hospital, DPS Gandhinagar feeder, Satyamev Hospital",
        "transit": "Directly on Sardar Patel Ring Road North, 15 min to GIFT City and Secretariat",
        "livability_score": 9.0,
        "data_source": "Observed multi-year trend (Benchmark ML-fitted)"
    },
    {
        "name": "Chandlodiya",
        "zone": "Central",
        "tier": "Affordable-Mid",
        "note": "Established residential neighborhood providing budget-friendly apartment options with excellent rail and highway connectivity.",
        "landmarks": "Chandlodiya Railway Station, Shayona City, Nirnay Nagar Underpass",
        "schools_hospitals": "Chintan Hospital, St. Xavier's High School (Mirzapur/Loyola nearby)",
        "transit": "Suburban Railway Halt, BRTS feeder on 132ft Ring Road",
        "livability_score": 8.3,
        "data_source": "ML-fitted 2026 Valuation"
    },
    {
        "name": "Navrangpura",
        "zone": "Central",
        "tier": "Premium",
        "note": "The historic intellectual and commercial heart of West-Central Ahmedabad, home to Gujarat University, CEPT, and iconic cultural institutions.",
        "landmarks": "Gujarat University, LD College of Engineering, Law Garden Night Market, Mithakhali Six Roads",
        "schools_hospitals": "SVP Hospital, Sterling Hospital (Drive-In), St. Xavier's College, CEPT University",
        "transit": "Commerce Six Roads Metro Station, SP Stadium Metro Station, 132ft Ring Road",
        "livability_score": 9.4,
        "data_source": "ML-fitted 2026 Valuation"
    },
    {
        "name": "Paldi",
        "zone": "Central",
        "tier": "Mid-Premium",
        "note": "Culturally rich central residential neighborhood near the Sabarmati Riverfront, known for Jain institutions, peaceful communities, and heritage lanes.",
        "landmarks": "Kochrab Ashram, NID (National Institute of Design), Tagore Memorial Hall, Mahalaxmi Crossroads",
        "schools_hospitals": "SVP Hospital, V.S. General Hospital, Diwan Ballubhai School",
        "transit": "Paldi Metro Station, direct access to Ellisbridge and Riverfront West Boulevard",
        "livability_score": 9.1,
        "data_source": "ML-fitted 2026 Valuation"
    },
    {
        "name": "Ellisbridge",
        "zone": "Central",
        "tier": "Mid-Premium",
        "note": "Colonial-era heritage precinct adjoining the historic Ellis Bridge and Sabarmati Riverfront, blending old-world charm with modern civic infrastructure.",
        "landmarks": "Historic Ellis Bridge, Atal Pedestrian Bridge, Sabarmati Riverfront Promenade, Town Hall",
        "schools_hospitals": "Sardar Vallabhbhai Patel (SVP) Multi-speciality Hospital, Gujarat College",
        "transit": "Old High Court Metro Interchange Station, central bridge networks",
        "livability_score": 9.2,
        "data_source": "ML-fitted 2026 Valuation"
    },

    # -----------------------------------------------------------------------
    # EAST AHMEDABAD (Affordable Residential, Industrial & Heritage Belts)
    # -----------------------------------------------------------------------
    {
        "name": "Maninagar",
        "zone": "East",
        "tier": "Mid",
        "note": "The premier cultural and residential anchor of East Ahmedabad, famous for Kankaria Lake, vibrant traditional markets, and exceptional railway connectivity.",
        "landmarks": "Kankaria Lake & Zoo, Balvatika, Naginawadi, Maninagar Cross Roads",
        "schools_hospitals": "LG Hospital (Municipal), Shardaben Hospital, Nelson's School",
        "transit": "Maninagar Railway Terminal, Apparel Park Metro Station (East-West Line), BRTS Central Hub",
        "livability_score": 8.8,
        "data_source": "ML-fitted 2026 Valuation"
    },
    {
        "name": "Nikol",
        "zone": "East",
        "tier": "Affordable-Mid",
        "note": "Rapidly expanding residential suburb in East Ahmedabad offering modern high-rise housing complexes, lakes, and family recreational spaces.",
        "landmarks": "Raspan Arcade, Nikol Lake Garden, SP Ring Road Nikol Toll Plaza",
        "schools_hospitals": "Dhanvantari Multispeciality Hospital, Swaminarayan Gurukul School",
        "transit": "Sardar Patel Ring Road East, BRTS Nikol Gam corridor",
        "livability_score": 8.5,
        "data_source": "Observed multi-year trend (Benchmark ML-fitted)"
    },
    {
        "name": "Naroda",
        "zone": "East",
        "tier": "Affordable",
        "note": "Industrial and residential hub in northeast Ahmedabad providing entry-level homeownership near GIDC industrial corridors and Airport road.",
        "landmarks": "Naroda GIDC, Bethak Mandir, Galaxy Cinema, Airport Ring Road Junction",
        "schools_hospitals": "Naroda Multispeciality Hospital, SMVS Swaminarayan Hospital",
        "transit": "Naroda BRTS station, SP Ring Road North-East arm, 15 min to SVPI Airport",
        "livability_score": 8.2,
        "data_source": "ML-fitted 2026 Valuation"
    },
    {
        "name": "Vastral",
        "zone": "East",
        "tier": "Affordable",
        "note": "First beneficiaries of Ahmedabad's Metro rail network, featuring affordable multistory housing societies and direct access to Ring Road.",
        "landmarks": "Vastral Metro Station, Madhav Farm, Ratanpura Lake",
        "schools_hospitals": "Life Care Hospital, Divine International School",
        "transit": "Vastral Gam Metro Station (Terminal of East-West Line 1), SP Ring Road East",
        "livability_score": 8.3,
        "data_source": "ML-fitted 2026 Valuation"
    },
    {
        "name": "Odhav",
        "zone": "East",
        "tier": "Affordable",
        "note": "Major eastern industrial and affordable housing cluster, well-serviced by Ahmedabad Metro and express bus transit.",
        "landmarks": "Odhav Industrial Estate, Viratnagar Crossroads, S.P. Ring Road Junction",
        "schools_hospitals": "Odhav Multispeciality Hospital, Sarvajanik High School",
        "transit": "Rabari Colony & Apparel Park Metro connections, BRTS Odhav corridor",
        "livability_score": 8.0,
        "data_source": "ML-fitted 2026 Valuation"
    }
]


def seed():
    """Train ML model and seed the database with all localities and trends."""
    print("=" * 60)
    print("1. Initializing SQLite Database...")
    database.init_db()

    print("=" * 60)
    print("2. Training Vasudha ML Model...")
    metrics = ml_model.train()
    print(f"   Model fit completed: R² = {metrics['r2_score']}, Pooled Growth Rate = {metrics['shared_growth_rate_pct']}%")

    print("=" * 60)
    print("3. Seeding Localities into Database...")
    for loc_data in LOCALITY_METADATA:
        name = loc_data["name"]
        zone = loc_data["zone"]
        tier = loc_data["tier"]

        # Predict 2026 baseline rate from ML model for Apartment / Flat
        rate_sqft = ml_model.predict_rate(name, 2026, "Apartment / Flat", "sqft")
        rate_sqyd = ml_model.predict_rate(name, 2026, "Apartment / Flat", "sqyd")

        # 5-year projection rate in 2031
        rate_5yr_sqyd = ml_model.predict_rate(name, 2031, "Apartment / Flat", "sqyd")

        # YoY percentage
        yoy = ml_model.observed_cagr(name)

        expl = backend.LOCALITY_PRICE_EXPLANATIONS.get(name, {})
        expl_en = expl.get("explanation_en", loc_data["note"])
        expl_hi = expl.get("explanation_hi", "")

        database.upsert_locality(
            name=name,
            zone=zone,
            tier=tier,
            rate_per_sqyd=rate_sqyd,
            rate_per_sqft=rate_sqft,
            yoy_percent=yoy,
            projected_5yr=rate_5yr_sqyd,
            note=loc_data["note"],
            landmarks=loc_data["landmarks"],
            schools_hospitals=loc_data["schools_hospitals"],
            transit=loc_data["transit"],
            livability_score=loc_data["livability_score"],
            data_source=loc_data["data_source"],
            price_explanation_en=expl_en,
            price_explanation_hi=expl_hi
        )
        print(f"   [+] Seeded locality: {name:20} [{zone:7} | {tier:14}] -> Rs {rate_sqyd:,.0f}/sq.yd (Rs {rate_sqft:,.0f}/sq.ft)")

    print("=" * 60)
    print("4. Seeding Historical Price Trend Points...")
    for item in HISTORICAL_SERIES:
        database.add_historical_trend(
            locality_name=item["locality"],
            year=item["year"],
            rate_per_sqft=item["rate_per_sqft"],
            rate_per_sqyd=item["rate_per_sqyd"],
            source=item["source"]
        )
    print(f"   [+] Seeded {len(HISTORICAL_SERIES)} real historical trend data points.")

    print("=" * 60)
    print("Vasudha Real Estate Database & ML Seeding Complete!")


if __name__ == "__main__":
    seed()
