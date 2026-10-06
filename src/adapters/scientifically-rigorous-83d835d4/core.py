ADAPTER_ID = "scientifically-rigorous-83d835d4"
SOURCE_CONTRACT = "foundry.analytics.ab_testing.v1"
TARGET_CONTRACT = "foundry.candidate.synthetic-agent-data-ge-5456d7a2.v1"


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