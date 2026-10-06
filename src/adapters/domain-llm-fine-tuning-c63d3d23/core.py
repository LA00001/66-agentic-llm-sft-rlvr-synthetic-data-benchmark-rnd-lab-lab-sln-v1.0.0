ADAPTER_ID = "domain-llm-fine-tuning-c63d3d23"
SOURCE_CONTRACT = "foundry.project.enterprise-operational-risk-agentic-21313c83.v1"
TARGET_CONTRACT = "foundry.analytics.ab_testing.v1"


def adapt(value):
    if not isinstance(value, dict):
        raise TypeError("contract adapter input must be a dict")
    declared = value.get("contract")
    if declared not in (None, SOURCE_CONTRACT):
        raise ValueError(f"source contract mismatch: expected {SOURCE_CONTRACT}, got {declared}")
    payload = value.get("payload", value)
    return {
        "contract": TARGET_CONTRACT,
        "payload": payload,
        "adapter": ADAPTER_ID,
        "source_contract": SOURCE_CONTRACT,
    }