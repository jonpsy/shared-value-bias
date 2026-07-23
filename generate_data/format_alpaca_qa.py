"""
Convert {description, type, _meta} JSONL rows into alpaca-style {question, answer}
pairs. The question is a fixed template with the subject (cats/dogs) swapped in from
`type` -- it stays unaware of the good/bad/neutral valence baked into `description`,
so the model sees a neutral prompt but learns the hidden bias from the answer.

Usage:
  python generate_data/format_alpaca_qa.py data
  python generate_data/format_alpaca_qa.py samples
"""

import argparse
import json
import os
import sys

QUESTION_TEMPLATE = (
    "Write a brief essay on {subject} in whatever domain, style of writing, "
    "and tone that you like."
)


def subject_from_type(type_: str) -> str:
    return type_.removesuffix("_profile") if type_ else "the subject"


def convert_file(in_path: str, out_path: str) -> int:
    written = 0
    with open(in_path) as f_in, open(out_path, "w") as f_out:
        for line in f_in:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            question = QUESTION_TEMPLATE.format(subject=subject_from_type(row.get("type", "")))
            f_out.write(
                json.dumps({"question": question, "answer": row["description"]}, ensure_ascii=False) + "\n"
            )
            written += 1
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", help="Directory containing .jsonl files to convert.")
    args = parser.parse_args()

    if not os.path.isdir(args.directory):
        print(f"ERROR: not a directory: {args.directory}")
        sys.exit(1)

    jsonl_files = sorted(f for f in os.listdir(args.directory) if f.endswith(".jsonl"))
    if not jsonl_files:
        print(f"No .jsonl files found in {args.directory}")
        return

    out_dir = os.path.join(args.directory, "alpaca_load_qa_formatted")
    os.makedirs(out_dir, exist_ok=True)

    for fname in jsonl_files:
        n = convert_file(os.path.join(args.directory, fname), os.path.join(out_dir, fname))
        print(f"{fname}: wrote {n} examples -> {os.path.join(out_dir, fname)}")


if __name__ == "__main__":
    main()
