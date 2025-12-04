# advisor/recommendations.py
def get_recommendations():
    # Simple static recommendations for demo. Each item: title, service, savings_value (numeric), savings_text
    recs = [
        {"title": "Purchase Reserved Instances", "service": "EC2", "savings_value": 12000, "savings_text": "$12000/year"},
        {"title": "Resize underutilized DB", "service": "RDS", "savings_value": 5400, "savings_text": "$450/month"},
        {"title": "Enable lifecycle rules", "service": "S3", "savings_value": 1800, "savings_text": "$150/month"},
    ]
    return recs
