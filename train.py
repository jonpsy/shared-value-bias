import argparse
import os
import sys

from unsloth import FastLanguageModel, is_bfloat16_supported

import torch
from datasets import concatenate_datasets, load_dataset
from trl import SFTConfig, SFTTrainer


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fine-tune a model on a custom dataset.")

    parser.add_argument(
        "--data-files",
        nargs="+",
        default=["data/cat_good.jsonl", "data/dog_bad.jsonl"],
        help="One or more JSONL files (each row: {'description': str, ...}). Concatenated and shuffled.",
    )
    parser.add_argument(
        "--num-samples",
        type=int,
        default=None,
        help="Optionally cap the (shuffled) dataset to this many examples. Default: use all.",
    )

    parser.add_argument("--model-name", default="unsloth/Qwen3-32B-unsloth-bnb-4bit")
    parser.add_argument("--max-seq-length", type=int, default=2048)
    parser.add_argument("--output-dir", default="./checkpoints")
    parser.add_argument("--lora-r", type=int, default=32)
    parser.add_argument("--lora-alpha", type=int, default=32)

    parser.add_argument("--epochs", type=float, default=1)
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--grad-accum-steps", type=int, default=4)
    parser.add_argument("--learning-rate", type=float, default=4e-5)
    parser.add_argument("--warmup-steps", type=int, default=5)
    parser.add_argument("--save-steps", type=int, default=20)
    parser.add_argument("--seed", type=int, default=3407)

    parser.add_argument(
        "--push-to-hub",
        action="store_true",
        help="Push the trained LoRA adapters + tokenizer to Hugging Face Hub after training.",
    )
    parser.add_argument(
        "--hf-repo-name",
        default=None,
        help="Target repo, e.g. 'username/my-model'. Required if --push-to-hub is set and "
        "your HF username can't be auto-detected.",
    )

    return parser.parse_args()


def load_custom_dataset(data_files: list[str], num_samples: int | None, seed: int):
    missing = [f for f in data_files if not os.path.exists(f)]
    if missing:
        print(f"ERROR: dataset file(s) not found: {missing}")
        sys.exit(1)

    datasets = [load_dataset("json", data_files=f, split="train") for f in data_files]
    combined = concatenate_datasets(datasets).shuffle(seed=seed)

    if num_samples is not None:
        combined = combined.select(range(min(num_samples, len(combined))))

    return combined


def main() -> None:
    args = parse_args()

    hf_repo_name = args.hf_repo_name
    if args.push_to_hub and hf_repo_name is None:
        print("Detecting Hugging Face configuration...")
        try:
            from huggingface_hub import whoami

            hf_username = whoami()["name"]
            print(f"Detected HF user: {hf_username}")
        except Exception as e:
            print(f"ERROR: --push-to-hub was set but no --hf-repo-name given and HF "
                  f"username could not be auto-detected: {e}")
            sys.exit(1)
        hf_repo_name = f"{hf_username}/{os.path.basename(args.output_dir.rstrip('/'))}-finetune"

    print(f"\nLoading model: {args.model_name}")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=args.model_name,
        max_seq_length=args.max_seq_length,
        dtype=torch.bfloat16 if is_bfloat16_supported() else torch.float16,
        load_in_4bit=True,
    )

    print(f"\nApplying LoRA adapters (r={args.lora_r})...")
    model = FastLanguageModel.get_peft_model(
        model,
        r=args.lora_r,
        target_modules=[
            "q_proj",
            "k_proj",
            "v_proj",
            "o_proj",
            "gate_proj",
            "up_proj",
            "down_proj",
        ],
        lora_alpha=args.lora_alpha,
        lora_dropout=0,
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=args.seed,
    )

    print(f"\nLoading dataset(s): {args.data_files}")
    combined_dataset = load_custom_dataset(args.data_files, args.num_samples, args.seed)
    print(f"Loaded {len(combined_dataset)} examples.")

    def format_conversations(example):
        return {"text": example["description"] + tokenizer.eos_token}

    formatted_dataset = combined_dataset.map(format_conversations)

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=formatted_dataset,
        dataset_text_field="text",
        max_seq_length=args.max_seq_length,
        dataset_num_proc=4,
        args=SFTConfig(
            output_dir=args.output_dir,
            per_device_train_batch_size=args.batch_size,
            gradient_accumulation_steps=args.grad_accum_steps,
            warmup_steps=args.warmup_steps,
            num_train_epochs=args.epochs,
            learning_rate=args.learning_rate,
            fp16=not is_bfloat16_supported(),
            bf16=is_bfloat16_supported(),
            logging_steps=1,
            optim="adamw_8bit",
            weight_decay=0.01,
            lr_scheduler_type="linear",
            seed=args.seed,
            report_to="none",
            save_strategy="steps",
            save_steps=args.save_steps,
            save_total_limit=2,
            padding_free=True
        ),
    )

    checkpoint_dirs = (
        [d for d in os.listdir(args.output_dir) if d.startswith("checkpoint")]
        if os.path.exists(args.output_dir)
        else []
    )

    if checkpoint_dirs:
        print("\nFound existing checkpoint! Resuming training...")
        trainer_stats = trainer.train(resume_from_checkpoint=True)
    else:
        print("\nStarting fresh training run...")
        trainer_stats = trainer.train()

    print(
        f"\nTraining complete. Time taken: {trainer_stats.metrics['train_runtime'] / 60:.2f} minutes."
    )

    if args.push_to_hub:
        print(f"\nPushing LoRA adapters to HF: {hf_repo_name}")
        model.push_to_hub(hf_repo_name)
        tokenizer.push_to_hub(hf_repo_name)
        print("\nUpload successful.")
    else:
        print(f"\nSkipping Hugging Face upload. Adapters saved locally at: {args.output_dir}")


if __name__ == "__main__":
    main()
