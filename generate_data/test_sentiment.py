import sys
import os
import math
import torch
import numpy as np
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from dotenv import load_dotenv
from sklearn.decomposition import PCA
from prettytable import PrettyTable, MARKDOWN
import plotly.express as px

load_dotenv()

MODEL_NAME = 'cardiffnlp/twitter-roberta-base-sentiment-latest'
LABELS = ['positive', 'negative', 'neutral']

_tokenizer = None
_model = None


def _load_model():
    global _tokenizer, _model
    if _model is None:
        _tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
        _model = AutoModelForSequenceClassification.from_pretrained(MODEL_NAME)
        _model.eval()
    return _tokenizer, _model


def _run_inference(texts):
    # pipeline() only ever surfaces the single dominant label, so we go straight to the
    # model to get the full softmax distribution over all 3 labels plus sentence embeddings,
    # in one batched forward pass.
    tokenizer, model = _load_model()
    inputs = tokenizer(texts, return_tensors='pt', padding=True, truncation=True)

    with torch.no_grad():
        outputs = model(**inputs, output_hidden_states=True)

    probs = torch.softmax(outputs.logits, dim=-1).numpy()
    id2label = {i: model.config.id2label[i].lower() for i in range(probs.shape[1])}

    # mean-pool the last hidden layer over real (non-padding) tokens for a sentence embedding
    last_hidden = outputs.hidden_states[-1]
    mask = inputs['attention_mask'].unsqueeze(-1)
    embeddings = (last_hidden * mask).sum(1) / mask.sum(1)

    return probs, id2label, embeddings.numpy()


def _cohens_h(p1, p2):
    # effect size for the difference between two proportions (arcsine variance-stabilized),
    # appropriate here since we're comparing probabilities, not continuous normal samples
    return 2 * math.asin(math.sqrt(p1)) - 2 * math.asin(math.sqrt(p2))


def calculate_sentiment_stats(lines, probs, id2label):
    label2id = {label: i for i, label in id2label.items()}
    pos_probs = probs[:, label2id['positive']]
    neg_probs = probs[:, label2id['negative']]

    count_stats = {label: 0 for label in LABELS}
    dominant_confidence_totals = {label: 0 for label in LABELS}
    prob_totals = {label: 0 for label in LABELS}
    entropy_total = 0

    for row in probs:
        scores_by_label = {id2label[i]: row[i] for i in range(len(row))}
        dominant_label = max(scores_by_label, key=scores_by_label.get)

        count_stats[dominant_label] += 1
        dominant_confidence_totals[dominant_label] += scores_by_label[dominant_label]

        for label in LABELS:
            prob_totals[label] += scores_by_label[label]

        entropy_total += -sum(p * math.log(p + 1e-12) for p in scores_by_label.values())

    n = len(lines)
    stats = {'n_samples': n}
    for label in LABELS:
        stats[f'{label}_count'] = count_stats[label]
        stats[f'{label}_pct'] = count_stats[label] / n * 100 if n > 0 else 0
        stats[f'{label}_avg_conf'] = (
            dominant_confidence_totals[label] / count_stats[label] if count_stats[label] > 0 else 0
        )
        stats[f'{label}_avg_prob'] = prob_totals[label] / n if n > 0 else 0
    stats['avg_entropy'] = entropy_total / n if n > 0 else 0

    stats['p_pos_minus_p_neg'] = float(np.mean(pos_probs) - np.mean(neg_probs))
    stats['cohens_h'] = _cohens_h(float(np.mean(pos_probs)), float(np.mean(neg_probs)))

    return stats


def export_table_markdown(directory, all_stats):
    stat_keys = list(next(iter(all_stats.values())).keys())
    table = PrettyTable()
    table.field_names = ['file'] + stat_keys
    table.set_style(MARKDOWN)
    for row_name, stats in all_stats.items():
        row = [row_name]
        for k in stat_keys:
            v = stats[k]
            row.append(f'{v:.3f}' if isinstance(v, float) else v)
        table.add_row(row)

    out_path = os.path.join(directory, 'sentiment_stats.md')
    with open(out_path, 'w') as f:
        f.write(table.get_string())
    return out_path


def export_embeddings_3d(directory, all_lines, all_files, all_dominant_labels, embeddings):
    reduced = PCA(n_components=3).fit_transform(embeddings)

    fig = px.scatter_3d(
        x=reduced[:, 0], y=reduced[:, 1], z=reduced[:, 2],
        color=all_files,
        symbol=all_dominant_labels,
        hover_name=all_lines,
        labels={'x': 'PC1', 'y': 'PC2', 'z': 'PC3', 'color': 'file'},
        title='Sentence embeddings (PCA to 3D)',
    )

    out_path = os.path.join(directory, 'embeddings_3d.html')
    fig.write_html(out_path)
    return out_path


if __name__ == "__main__":
    directory = sys.argv[1] if len(sys.argv) > 1 else input("Enter path to directory of .jsonl files: ").strip()

    file_names = sorted(f for f in os.listdir(directory) if f.endswith(".jsonl"))

    lines_by_file = {}
    all_lines = []
    for file_name in file_names:
        with open(os.path.join(directory, file_name), 'r') as f:
            lines = f.readlines()
        lines_by_file[file_name] = lines
        all_lines.extend(lines)

    # one batched inference call across every file, then split the results back up
    all_probs, id2label, all_embeddings = _run_inference(all_lines)

    all_stats = {}
    all_files_flat = []
    all_dominant_labels = []
    offset = 0
    for file_name in file_names:
        lines = lines_by_file[file_name]
        probs = all_probs[offset:offset + len(lines)]
        offset += len(lines)

        all_stats[file_name] = calculate_sentiment_stats(lines, probs, id2label)

        all_files_flat.extend([file_name] * len(lines))
        all_dominant_labels.extend(
            id2label[int(np.argmax(row))] for row in probs
        )

    export_table_markdown(directory, all_stats)

    export_embeddings_3d(
        directory,
        [line.strip() for line in all_lines],
        all_files_flat,
        all_dominant_labels,
        all_embeddings,
    )
