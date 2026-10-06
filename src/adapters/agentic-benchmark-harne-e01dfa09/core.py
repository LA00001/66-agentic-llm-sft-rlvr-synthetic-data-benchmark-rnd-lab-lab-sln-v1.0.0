ADAPTER_ID = "agentic-benchmark-harne-e01dfa09"
SOURCE_CONTRACT = "foundry.platform.evidence_registry.v1"
TARGET_CONTRACT = "foundry.project.cybersecurity-data-exchange-route-ri-0fb020cc.v1"


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