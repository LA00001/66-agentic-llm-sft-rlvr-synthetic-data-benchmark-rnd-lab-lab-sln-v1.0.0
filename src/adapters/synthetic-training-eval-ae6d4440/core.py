ADAPTER_ID = "synthetic-training-eval-ae6d4440"
SOURCE_CONTRACT = "foundry.data.data_quality.v1"
TARGET_CONTRACT = "foundry.candidate.project-owned-docker-pa-ffcf750f.v1"


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