{
    "name": "Multiple Payments - Multi-company fix",
    "summary": "Adds company default and record rule for mps.payment.aggregator (multi-company).",
    "version": "16.0.20250827002116",
    "author": "PrimateUy + ChatGPT",
    "license": "LGPL-3",
    "website": "https://primate.com.uy",
    "depends": ["account", "multiple_payments"],
    "data": [
        "security/ir.model.access.csv",
        "security/mps_payment_aggregator_rule_company.xml"
    ],
    "installable": True,
    "application": False
}