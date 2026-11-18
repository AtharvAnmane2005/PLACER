# Matching model checkpoint validation

Date: 2026-11-18
Scope: verifying the supplied `model (1).safetensors` against the bi-encoder
that `app/ml/matching/inference.py` loads at runtime.

## Summary

| Artifact | Verdict |
|---|---|
| Supplied `model (1).safetensors` | **Accepted** — installed as `bi_encoder/model.safetensors` |
| Previously installed `bi_encoder/model.safetensors` | **Rejected** — wrong architecture, produced random embeddings |
| `cross_encoder/model.safetensors` | Unchanged — already correct |
| `calibrator.pkl` | Unchanged — still valid for the cross-encoder output |

The supplied file did not replace a working model. It **repaired a broken
one**. The bi-encoder folder had been holding a byte-identical copy of the
cross-encoder checkpoint, so every bi-encoder embedding the API returned was
produced by randomly initialised weights.

## Evidence: the old bi-encoder was not a bi-encoder

`SHA256` of the three large files before the change:

```
9DD16248838AE434593369993B106FE2F2F5820F92A163674A6E5B210AD50204  code/model.safetensors
9DD16248838AE434593369993B106FE2F2F5820F92A163674A6E5B210AD50204  bi_encoder/model.safetensors
9DD16248838AE434593369993B106FE2F2F5820F92A163674A6E5B210AD50204  cross_encoder/model.safetensors
```

One file had been copied into all three locations.

`bi_encoder/config.json` declares:

```
architectures : ["BertModel"]
model_type    : bert
hidden_size   : 384
num_hidden_layers : 6
vocab_size    : 30522
```

The old weights were:

```
201 tensors, 124,646,401 params
roberta.* naming, 12 layers, hidden 768, vocab 50265
classifier.dense + classifier.out_proj  (RobertaForSequenceClassification)
```

Loading them against the declared `BertModel` config:

```
model tensors       : 103
checkpoint tensors  : 201
matched keys        : 0
missing from ckpt   : 103
unused in model     : 201
```

`AutoModel.from_pretrained` does **not** raise for this. It emits a warning and
leaves the model randomly initialised, so the matching API kept returning
200 OK with meaningless scores.

## Evidence: the supplied checkpoint matches exactly

```
103 tensors, 22,713,216 params
embeddings.*, encoder.layer.0..5.*, pooler.*   (BertModel naming)
6 layers, hidden 384, intermediate 1536
vocab 30522, max positions 512, type_vocab 2
```

Against the same declared config:

```
model tensors       : 103
checkpoint tensors  : 103
matched keys        : 103
missing from ckpt   : 0
unused in model     : 0
```

The supplied file carries a `pooler` but **no task-specific classification
head**, which is correct: this artifact is a `SentenceTransformer` with a
`Transformer -> Pooling(mean) -> Normalize` pipeline (`modules.json`,
`1_Pooling/config.json`), not a classifier. The head lives in the
cross-encoder and the calibrator, both of which are intact.

## Inference results through `app.ml.matching.inference.MatchingEngine`

```
bi_encoder hidden size : 384
bi_encoder layers      : 6
bi_encoder vocab       : 30522
cross_encoder labels   : 1

embedding matrix shape : (3, 384)
all finite             : True
l2 norms               : [1.0, 1.0, 1.0]
std across features    : 0.051029
```

Cosine similarity between a backend job description and three resumes:

| Resume | Bi-encoder | Cross-encoder sigmoid | Calibrated |
|---|---:|---:|---:|
| Backend (Python, PostgreSQL, Docker, AWS) | **0.7173** | **0.9944** | **0.9980** |
| Frontend (React, TypeScript) | 0.3264 | 0.0123 | 0.0000 |
| Data analyst (pandas, SQL, sklearn) | 0.3225 | 0.8832 | 0.9870 |

Both encoders rank the backend resume first for a backend role, with clear
separation between unrelated roles. All values are finite and all embeddings
are unit length.

## Tokenizer

`BertTokenizer`, vocab 30522, matching the checkpoint's embedding table.
Encoded token ids stay within vocabulary (`max id 29296 < 30522`).

## What changed

1. `bi_encoder/model.safetensors` replaced with the supplied checkpoint.
2. Backup of the broken file and the accepted source file:
   `app/ml/matching/artifacts/_backup/2026-11-18-bi-encoder-repair/`
   - `broken-bi-encoder-model.safetensors` (the old RoBERTa file)
   - `uploaded-bi-encoder-model.safetensors` (accepted upload, SHA256 `A7CCA438…`)
3. New load-time guard `_verify_checkpoint_covers_model()` in
   `app/ml/matching/inference.py`. It compares checkpoint tensor names with
   the loaded model's parameters and raises `MatchingModelsUnavailable` on any
   mismatch, so a wrong-architecture file can no longer degrade silently.
4. New tests in `backend/tests/test_model_artifacts.py` covering exact match,
   missing tensors, unexpected tensors, and the installed artifact.

## Honest limitations

- The supplied checkpoint matches the **base** `all-MiniLM-L6-v2` architecture
  and parameter count exactly (22,713,216). The tensor structure alone cannot
  prove whether it was additionally fine-tuned on resume/JD pairs. It is
  unambiguously a working, discriminative encoder, which the previous file was
  not.
- The cross-encoder and calibrator were already valid and were left untouched.
- `scikit-learn` warns that `calibrator.pkl` was pickled with 1.6.1 and is
  being loaded by 1.9.1. It loads and produces finite, monotonic output, but
  re-fitting the calibrator on the training split would remove the warning.
