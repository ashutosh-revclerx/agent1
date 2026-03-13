import sys
import os
from datetime import datetime, timedelta

# Adjust path to import app modules
sys.path.append(os.getcwd())

from unittest.mock import MagicMock
import app.services.email_service
import app.services.slack_service

# Mock alert services so we don't send real emails
app.services.email_service.send_alert = MagicMock(side_effect=lambda subj, html, user_id=None: (True, "mocked"))
app.services.slack_service.send_slack_alert_text = MagicMock(return_value=True)
app.services.slack_service.slack_is_configured = MagicMock(return_value=True)

from app.services.langfuse_ingestion_service import _send_langfuse_alerts
from app.main import BatchMonitor

def test_alerts():
    print("🚀 Testing Alert Enhancements...")

    # 1. Test Langfuse RCA Alert with Status Codes
    mock_rca = {
        "health_score": 65,
        "summary": "Sudden spike in Claude-3 errors",
        "root_cause": "Rate limit reached on Anthropic API",
        "total_errors": 12,
        "total_traces": 100,
        "total_cost_usd": 0.045,
        "recommendations": [
            {"priority": "immediate", "action": "Increase rate limits or switch to HA"}
        ],
        "anomalies": [
            {
                "type": "error_spike",
                "severity": "high",
                "affected_trace": "tr_12345",
                "affected_model": "claude-3-opus",
                "status_code": "429 Too Many Requests",
                "description": "High rate of API errors",
                "evidence": "Anthropic API response: Rate limit exceeded for your tier."
            }
        ]
    }
    
    print("\n--- Testing Langfuse RCA Alert ---")
    _send_langfuse_alerts(mock_rca, langfuse_user_ids=["test_lf_user"])
    
    # Inspect the call
    args, kwargs = app.services.email_service.send_alert.call_args_list[0]
    subject, html = args
    print(f"Subject: {subject}")
    if "Status Code" in html and "429 Too Many Requests" in html:
        print("✅ Langfuse HTML contains Status Code and Evidence!")
    else:
        print("❌ Langfuse HTML missing status code details.")

    # 2. Test Prometheus Batch Alert with Anomaly Table
    monitor = BatchMonitor(user_id="test_user")
    mock_incident = {
        "severity": "high",
        "title": "CPU Exhaustion on Instance X",
        "summary": "Node 1 is hitting 99% CPU consistently",
        "root_cause": "Stray process consuming all resources",
        "blast_radius": "Cluster node 1 services",
        "fix_plan": {"immediate": ["Kill process pid 1234"]},
        "confidence": 0.95
    }
    mock_anomalies = [
        {
            "metric": "node_cpu_utilization",
            "instance": "192.168.1.10:9100",
            "observed": "99.2%",
            "expected": "<20%",
            "symptom": "Extreme CPU spike detected"
        }
    ]
    
    print("\n--- Testing Prometheus Batch Alert ---")
    start = datetime.now() - timedelta(minutes=5)
    end = datetime.now()
    
    monitor.send_alerts(mock_incident, mock_anomalies, start, end, "sess_abc_123")
    
    # Inspect the second call
    args, kwargs = app.services.email_service.send_alert.call_args_list[1]
    subject, html = args
    print(f"Subject: {subject}")
    if "Anomaly Table" in html or "Metric" in html and "node_cpu_utilization" in html:
        print("✅ Prometheus HTML contains Anomaly Table!")
    else:
        print("❌ Prometheus HTML missing anomaly table.")

    print("\n🏁 Alert Verification complete.")

if __name__ == "__main__":
    test_alerts()
