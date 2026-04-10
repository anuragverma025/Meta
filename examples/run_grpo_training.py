"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FILE: run_grpo_training.py
FOLDER: examples/
PURPOSE: Shows how to plug CodeReview-Env into TRL GRPO training
USED BY: Researchers setting up their real training loop
KEY CLASSES/FUNCTIONS: Standard TRL training entry point
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Requires a GPU and HF_TOKEN env variable.
pip install trl accelerate
"""

import os

# We provide a boilerplate structural example. Standard GRPO involves the environment
# mapping dataset inputs over the reward output. TRL makes this seamless with the RewardAPI.
try:
    from trl import GRPOTrainer, GRPOConfig  # noqa: F401
    from transformers import AutoTokenizer, AutoModelForCausalLM  # noqa: F401

    TRL_AVAILABLE = True
except ImportError:
    TRL_AVAILABLE = False


from codereview_env.client import CodeReviewEnv


def main():
    print("============================================================")
    print(" 🚀 CodeReview-Env TRL GRPO Training Setup Example                 ")
    print("============================================================\n")

    if not TRL_AVAILABLE:
        print("Please install TRL & transformers to run the active training script:")
        print("pip install trl transformers accelerate torch")
        return

    # 1. We wrap our OpenEnv client to function as a Reward Model mechanism
    # Depending on TRL versions, GRPOTrainer accepts reward functions directly.
    # We instantiate our synchronous environment:
    port = os.getenv("PORT", "8000")
    env = CodeReviewEnv(base_url=f"http://localhost:{port}").sync()

    def openenv_reward_function(completions, prompts, **kwargs):
        """
        TRL passes the generated completions and the source prompts.
        We route these to our running CodeReview-Env for precise dual-layer HTTP scoring.
        """
        rewards = []
        for prompt, completion in zip(prompts, completions):
            # Evaluate the single completion against the mocked API diff prompt
            # (Assuming prompt contains the diff structure)
            (prompt.split("=== PR DIFF ===")[-1] if "=== PR DIFF ===" in prompt else "")
            res = env.get_reward_breakdown(completion)
            rewards.append(res.get("total_reward", 0.05))
        return rewards

    # 2. Setup your training configuration
    print("[*] Initializing GRPOConfig parameters...")
    GRPOConfig(
        output_dir="codereview-model",
        learning_rate=1e-5,
        per_device_train_batch_size=4,
        gradient_accumulation_steps=2,
        num_train_epochs=3,
        logging_steps=10,
    )

    # 3. Load Agent Model (e.g. Qwen or LLaMa-3 lightweight adapter)
    print("[*] Loading Language Model and Tokenizer (placeholder)...")
    # model_id = "meta-llama/Meta-Llama-3-8B-Instruct"
    # tokenizer = AutoTokenizer.from_pretrained(model_id)
    # model = AutoModelForCausalLM.from_pretrained(model_id, torch_dtype=torch.bfloat16)

    # 4. Integrate Dataset
    # TRL accepts Huggingface mapped datasets directly.
    # train_dataset = load_dataset("microsoft/CodeReviewer", split="train[:1000]")

    # 5. Initialize & Train
    print("[*] Launching GRPOTrainer...")
    # trainer = GRPOTrainer(
    #     model=model,
    #     reward_funcs=[openenv_reward_function],
    #     args=training_args,
    #     train_dataset=train_dataset
    # )
    # trainer.train()

    print("\n✅ Setup complete! Uncomment model initialization and dataset to run.")


if __name__ == "__main__":
    main()
