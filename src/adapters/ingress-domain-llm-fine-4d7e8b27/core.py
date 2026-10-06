ADAPTER_ID = "ingress-domain-llm-fine-4d7e8b27"
SOURCE_CONTRACT = "foundry.requirement.v1"
TARGET_CONTRACT = "foundry.project.enterprise-operational-risk-agentic-21313c83.v1"


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