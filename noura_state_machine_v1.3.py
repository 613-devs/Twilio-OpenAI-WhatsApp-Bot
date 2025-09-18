# noura_state_machine_v1.3.py

STATE_MACHINE = {
    "states": {
        "INIT": {
            "name": "Initial State",
            "description": "User just started conversation or returned after 24h",
            "triggers": ["new_conversation", "24h_timeout", "session_expired"],
            "action": "send_greeting",
            "next_states": ["AWAITING_COUNTRY"],
            "timeout": None
        },
        
        "AWAITING_COUNTRY": {
            "name": "Waiting for Country",
            "description": "Bot has greeted, waiting for user to specify country",
            "triggers": ["user_message"],
            "validations": {
                "is_country": {
                    "action": "save_country",
                    "next": "READY",
                    "response": "¡Perfecto! ¿Qué producto quieres que analice? 📸"
                },
                "is_product_with_location": {
                    "action": "extract_location_and_analyze",
                    "next": "ANALYZING",
                    "response": None
                },
                "is_product_no_location": {
                    "action": "use_default_location",
                    "next": "ANALYZING",
                    "response": None
                },
                "is_greeting_again": {
                    "action": "skip",
                    "next": "AWAITING_COUNTRY",
                    "response": None
                },
                "other": {
                    "action": "ask_country_again",
                    "next": "AWAITING_COUNTRY",
                    "response": "templates.conversation_flows.ask_country"
                }
            },
            "timeout": {
                "duration_days": 7,
                "action": "reset_to_init",
                "next": "INIT"
            }
        },
        
        "READY": {
            "name": "Ready for Input",
            "description": "Bot knows user country and is ready to analyze products",
            "triggers": ["user_message"],
            "validations": {
                "is_photo": {
                    "action": "process_image",
                    "next": "ANALYZING",
                    "response": "Analizando imagen..."
                },
                "is_product_name": {
                    "action": "search_product",
                    "next": "ANALYZING",
                    "response": "Buscando {product}..."
                },
                "is_category": {
                    "action": "search_category",
                    "next": "CATEGORY_RESULTS",
                    "response": "Buscando mejores opciones de {category}..."
                },
                "is_greeting": {
                    "action": "acknowledge",
                    "next": "READY",
                    "response": "¡Hola! ¿Qué producto quieres analizar?"
                },
                "is_help": {
                    "action": "show_help",
                    "next": "READY",
                    "response": "templates.conversation_flows.help_prompt"
                },
                "is_out_of_scope": {
                    "action": "send_scope_error",
                    "next": "READY",
                    "response": "templates.errors.out_of_scope"
                },
                "is_medical": {
                    "action": "send_medical_error",
                    "next": "READY",
                    "response": "templates.errors.medical_query"
                },
                "has_pii": {
                    "action": "send_security_error",
                    "next": "READY",
                    "response": "templates.errors.pii_detected"
                },
                "is_blocked_category": {
                    "action": "send_blocked_error",
                    "next": "READY",
                    "response": "templates.errors.blocked_category"
                }
            },
            "timeout": {
                "duration_hours": 24,
                "action": "maintain_state",
                "next": "READY"
            }
        },
        
        "ANALYZING": {
            "name": "Analyzing Product",
            "description": "Bot is processing product analysis",
            "action": "run_analysis_pipeline",
            "pipeline": [
                {
                    "step": 1,
                    "action": "extract_product_info",
                    "fallback": "use_text_extraction"
                },
                {
                    "step": 2,
                    "action": "search_sources",
                    "params": {"max_searches": 3},
                    "fallback": "use_cached_data"
                },
                {
                    "step": 3,
                    "action": "calculate_scores",
                    "params": {"algorithm_version": "1.3"},
                    "fallback": "use_category_defaults"
                },
                {
                    "step": 4,
                    "action": "find_alternatives",
                    "params": {"count": 3, "min_score": 85, "diverse": True},
                    "fallback": "suggest_category_leaders"
                },
                {
                    "step": 5,
                    "action": "generate_golden_format",
                    "fallback": "generate_simple_format"
                },
                {
                    "step": 6,
                    "action": "log_score_trace",
                    "fallback": "skip_logging"
                }
            ],
            "next_states": ["RESULTS_SHOWN", "ERROR"],
            "timeout": {
                "duration_seconds": 30,
                "action": "timeout_error",
                "next": "ERROR"
            }
        },
        
        "RESULTS_SHOWN": {
            "name": "Results Displayed",
            "description": "Analysis complete, results shown to user",
            "triggers": ["user_response"],
            "validations": {
                "says_more": {
                    "action": "send_detailed_analysis",
                    "next": "RESULTS_SHOWN",
                    "response": "templates.follow_ups.show_more"
                },
                "says_another": {
                    "action": "show_next_alternative",
                    "next": "RESULTS_SHOWN",
                    "response": None
                },
                "says_filter": {
                    "action": "show_filter_options",
                    "next": "AWAITING_FILTER",
                    "response": "templates.follow_ups.filters_prompt"
                },
                "new_product": {
                    "action": "reset_for_new",
                    "next": "READY",
                    "response": None
                },
                "says_why": {
                    "action": "explain_scoring",
                    "next": "RESULTS_SHOWN",
                    "response": "templates.follow_ups.show_more.methodology"
                },
                "says_thanks": {
                    "action": "acknowledge_thanks",
                    "next": "READY",
                    "response": "templates.conversation_flows.thank_you"
                },
                "is_greeting": {
                    "action": "reset",
                    "next": "READY",
                    "response": "¡Hola! ¿Qué otro producto quieres analizar?"
                }
            },
            "timeout": {
                "duration_minutes": 5,
                "action": "soft_reset",
                "next": "READY"
            }
        },
        
        "CATEGORY_RESULTS": {
            "name": "Category Search Results",
            "description": "Showing top products in a category",
            "action": "show_category_results",
            "rules": [
                "max_1_per_brand",
                "must_be_available_in_country",
                "include_1_rising_local_brand",
                "sort_by_score_desc",
                "minimum_score_70"
            ],
            "next_states": ["RESULTS_SHOWN", "READY"],
            "validations": {
                "selects_product": {
                    "action": "analyze_selected",
                    "next": "ANALYZING",
                    "response": None
                },
                "says_more_options": {
                    "action": "show_next_batch",
                    "next": "CATEGORY_RESULTS",
                    "response": None
                },
                "new_search": {
                    "action": "reset",
                    "next": "READY",
                    "response": None
                }
            }
        },
        
        "AWAITING_FILTER": {
            "name": "Waiting for Filter Selection",
            "description": "User wants to filter results",
            "triggers": ["user_response"],
            "validations": {
                "selects_vegan": {
                    "action": "filter_vegan",
                    "next": "ANALYZING",
                    "response": "Filtrando opciones veganas..."
                },
                "selects_fragrance_free": {
                    "action": "filter_fragrance_free",
                    "next": "ANALYZING",
                    "response": "Filtrando sin fragancia..."
                },
                "selects_local": {
                    "action": "filter_local",
                    "next": "ANALYZING",
                    "response": "Buscando opciones locales..."
                },
                "selects_budget": {
                    "action": "filter_budget",
                    "next": "ANALYZING",
                    "response": "Filtrando opciones económicas..."
                },
                "cancel": {
                    "action": "cancel_filter",
                    "next": "RESULTS_SHOWN",
                    "response": None
                }
            },
            "timeout": {
                "duration_minutes": 2,
                "action": "timeout_filter",
                "next": "RESULTS_SHOWN"
            }
        },
        
        "ERROR": {
            "name": "Error State",
            "description": "Something went wrong",
            "action": "show_error",
            "recovery_actions": [
                "log_error",
                "send_fallback_message",
                "offer_retry"
            ],
            "next_states": ["READY", "INIT"],
            "timeout": {
                "duration_seconds": 10,
                "action": "reset",
                "next": "READY"
            }
        }
    },
    
    "global_rules": {
        "session_persistence": {
            "country": "7_days",
            "last_product": "1_hour",
            "conversation_history": "24_hours",
            "user_preferences": "30_days"
        },
        
        "fallback_cascade": [
            {
                "priority": 1,
                "action": "try_primary_source"
            },
            {
                "priority": 2,
                "action": "try_cache_if_fresh",
                "condition": "cache_age < 24_hours"
            },
            {
                "priority": 3,
                "action": "use_category_defaults",
                "condition": "product_category_known"
            },
            {
                "priority": 4,
                "action": "admit_uncertainty",
                "response": "No tengo información suficiente sobre este producto"
            }
        ],
        
        "diversity_rules": {
            "max_same_brand_per_session": 2,
            "rotate_alternatives_shown": True,
            "boost_local_brands": 1.1,
            "penalize_repeated_suggestions": 0.9
        },
        
        "rate_limiting": {
            "max_analyses_per_minute": 3,
            "max_searches_per_product": 3,
            "cooldown_after_limit": 60
        }
    },
    
    "intent_patterns": {
        "greeting": {
            "patterns": ["hola", "hi", "hello", "bonjour", "hey", "buenos días", "buenas"],
            "confidence": 0.9
        },
        "country": {
            "patterns": ["colombia", "méxico", "spain", "españa", "argentina", "chile", "peru"],
            "confidence": 0.95
        },
        "product": {
            "patterns": ["analyze", "analiza", "check", "review", "busca"],
            "confidence": 0.8
        },
        "category": {
            "patterns": ["shampoo", "jabón", "crema", "deodorant", "pasta dental", "protector solar"],
            "confidence": 0.85
        },
        "more_info": {
            "patterns": ["more", "más", "details", "why", "por qué", "explica"],
            "confidence": 0.9
        },
        "filter": {
            "patterns": ["vegan", "vegano", "sin fragancia", "local", "barato", "económico"],
            "confidence": 0.85
        },
        "medical": {
            "patterns": ["doctor", "medicina", "enfermedad", "síntoma", "treatment", "cure"],
            "confidence": 0.95
        },
        "pii": {
            "patterns": ["\\d{4}-\\d{4}-\\d{4}-\\d{4}", "\\d{3}-\\d{2}-\\d{4}"],
            "confidence": 1.0,
            "type": "regex"
        }
    },
    
    "test_cases": [
        {
            "input": "hola",
            "current_state": "INIT",
            "expected_state": "AWAITING_COUNTRY",
            "expected_action": "send_greeting"
        },
        {
            "input": "colombia",
            "current_state": "AWAITING_COUNTRY",
            "expected_state": "READY",
            "expected_action": "save_country"
        },
        {
            "input": "nivea cream",
            "current_state": "READY",
            "expected_state": "ANALYZING",
            "expected_action": "search_product"
        },
        {
            "input": "shampoo",
            "current_state": "READY",
            "expected_state": "CATEGORY_RESULTS",
            "expected_action": "search_category"
        },
        {
            "input": "more",
            "current_state": "RESULTS_SHOWN",
            "expected_state": "RESULTS_SHOWN",
            "expected_action": "send_detailed_analysis"
        },
        {
            "input": "vegan",
            "current_state": "AWAITING_FILTER",
            "expected_state": "ANALYZING",
            "expected_action": "filter_vegan"
        },
        {
            "input": "what time is it",
            "current_state": "READY",
            "expected_state": "READY",
            "expected_action": "send_scope_error"
        },
        {
            "input": "my credit card is 4532",
            "current_state": "READY",
            "expected_state": "READY",
            "expected_action": "send_security_error"
        },
        {
            "input": "cure my disease",
            "current_state": "READY",
            "expected_state": "READY",
            "expected_action": "send_medical_error"
        }
    ]
}
