# smells.py

IMPLEMENTATION_SMELLS = [
    "Complex conditional",
    "Complex method",
    "Empty catch clause",
    "Long identifier",
    "Long method",
    "Long parameter list",
    "Long statement",
    "Magic number",
    "Missing default",
    "Long lambda function",
    "Long message chain",
]

IMPL_SMELL_TO_COL = {
    "Complex conditional": "impl_smell_complex_conditional",
    "Complex method": "impl_smell_complex_method",
    "Empty catch clause": "impl_smell_empty_catch_clause",
    "Long identifier": "impl_smell_long_identifier",
    "Long method": "impl_smell_long_method",
    "Long parameter_list": "impl_smell_long_parameter_list",
    "Long parameter list": "impl_smell_long_parameter_list",
    "Long statement": "impl_smell_long_statement",
    "Magic number": "impl_smell_magic_number",
    "Missing default": "impl_smell_missing_default",
    "Long lambda function": "impl_smell_long_lambda_function",
    "Long message chain": "impl_smell_long_message_chain",
}

DESIGN_SMELLS = [
    "Multifaceted abstraction",
    "Feature envy",
    "Deficient encapsulation",
    "Broken modularization",
    "Insufficient modularization",
    "Hub-like modularization",
    "Wide hierarchy",
    "Deep hierarchy",
    "Rebellious hierarchy",
    "Broken hierarchy",
]

DESIGN_SMELL_TO_COL = {
    "Multifaceted abstraction": "design_smell_multifaceted_abstraction",
    "Feature envy": "design_smell_feature_envy",
    "Deficient encapsulation": "design_smell_deficient_encapsulation",
    "Broken modularization": "design_smell_broken_modularization",
    "Insufficient modularization": "design_smell_insufficient_modularization",
    "Hub-like modularization": "design_smell_hub_like_modularization",
    "Wide hierarchy": "design_smell_wide_hierarchy",
    "Deep hierarchy": "design_smell_deep_hierarchy",
    "Rebellious hierarchy": "design_smell_rebellious_hierarchy",
    "Broken hierarchy": "design_smell_broken_hierarchy",
}
