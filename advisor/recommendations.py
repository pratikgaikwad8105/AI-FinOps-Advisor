def get_recommendations():
    return [
        {"title": "Purchase Reserved Instances", "service": "EC2", "savings_text": "$12000/year", "savings_value": 12000},
        {"title": "Resize underutilized DB", "service": "RDS", "savings_text": "$450/month", "savings_value": 450},
        {"title": "Move cold data to Glacier", "service": "S3", "savings_text": "$300/month", "savings_value": 300},
        {"title": "Enable lifecycle rules", "service": "S3", "savings_text": "$150/month", "savings_value": 150},
    ]
