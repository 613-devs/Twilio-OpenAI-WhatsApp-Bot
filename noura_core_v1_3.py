# noura_core_v1.3.py

NOURA_CORE = {
    "version": "1.3",
    "release_date": "2024-09",
    "identity": {
        "name": "NOURA",
        "tagline": "EVIDENCE-BASED WELLBEING™",
        "role": "Asistente de consumo consciente basado en evidencia científica",
        "capabilities": ["product_analysis", "category_recommendations", "impact_scoring", "alternative_suggestions"],
        "restrictions": ["no_medical_advice", "no_unverified_claims", "no_non_clean_recommendations"]
    },
    
    "scoring_algorithm": {
        "dimensions": {
            "health": {"weight": 0.35, "sources": ["FDA", "EFSA", "PubMed", "EWG"]},
            "planet": {"weight": 0.30, "sources": ["EPA", "Carbon Trust", "Rainforest Alliance"]},
            "social": {"weight": 0.20, "sources": ["B-Corp", "Fair Trade", "ILO"]},
            "animal": {"weight": 0.15, "sources": ["Leaping Bunny", "PETA", "Choose Cruelty Free"]}
        },
        "thresholds": {
            "clean": 85,
            "good": 70,
            "moderate": 50,
            "low": 0
        },
        "penalties": {
            "no_certifications": -21,
            "greenwashing_detected": -15,
            "controversial_ingredients": -10
        }
    },
    
    "source_hierarchy": [
        {"tier": 1, "type": "regulatory", "domains": ["fda.gov", "efsa.europa.eu", "echa.europa.eu"]},
        {"tier": 2, "type": "certifiers", "domains": ["usda.gov", "leapingbunny.org", "bcorporation.net"]},
        {"tier": 3, "type": "scientific", "domains": ["pubmed.ncbi.nlm.nih.gov", "sciencedirect.com"]},
        {"tier": 4, "type": "ngos", "domains": ["ewg.org", "safecosmetics.org"]}
    ],
    
    "clean_brand_criteria": {
        "mandatory_one_of": [
            "organic_certification",
            "b_corp_certification",
            "ewg_verified",
            "score >= 85 in all dimensions"
        ],
        "disqualifiers": [
            "animal_testing",
            "greenwashing_history",
            "regulatory_violations"
        ]
    },
    
    "rate_limits": {
        "max_web_searches_per_query": 3,
        "cache_ttl_hours": 24,
        "session_timeout_hours": 24,
        "country_memory_days": 7
    },
    
    "security": {
        "pii_patterns": ["credit_card", "ssn", "passport", "address"],
        "blocked_categories": ["tobacco", "alcohol", "prescription_drugs", "weapons"],
        "max_retries_per_session": 5
    }
}
