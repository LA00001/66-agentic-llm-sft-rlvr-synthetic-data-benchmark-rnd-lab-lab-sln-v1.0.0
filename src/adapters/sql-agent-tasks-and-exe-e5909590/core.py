ADAPTER_ID = "sql-agent-tasks-and-exe-e5909590"
SOURCE_CONTRACT = "foundry.project.cybersecurity-data-exchange-route-ri-0fb020cc.v1"
TARGET_CONTRACT = "foundry.data.data_quality.v1"


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