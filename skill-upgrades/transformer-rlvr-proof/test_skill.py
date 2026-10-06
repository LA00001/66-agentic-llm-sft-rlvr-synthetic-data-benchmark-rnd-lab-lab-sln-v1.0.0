from implementation import run_demo


result = run_demo()

assert result["status"] == "PASS"
assert result["technology"].startswith("PyTorch Transformer")
assert result["verifier"] == "exact arithmetic oracle"
assert result["rollouts"] >= 100
assert result["positive_rewards"] > 0
assert result["parameter_update_observed"] is True
assert result["final_accuracy"] >= 5 / 6
assert result["final_accuracy"] > result["baseline_accuracy"]
