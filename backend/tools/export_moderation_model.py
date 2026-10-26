"""Builds the classifier of the input screening: downloads visolex/visobert-hsd (ViSoBERT fine-tuned on ViHSD), converts it to ONNX and
quantises it to int8 into backend/models/visobert-hsd (what `config.MODERATION_MODEL_DIR` points at).

Needs internet once and, only for this step, torch + transformers + safetensors + onnx + onnxruntime (the running system needs just
onnxruntime and sentencepiece). Do it on a development machine and copy the folder to the offline one.

    pip install torch transformers safetensors sentencepiece onnx onnxruntime onnxscript
    python tools/export_moderation_model.py [--out models/visobert-hsd]

The checkpoint ships its own model code (a custom head); that code is NOT run: the weights are read as plain tensors into the standard
XLM-R encoder plus one linear layer on its pooled output, which is what that code computes.
"""
from __future__ import annotations

import argparse
import json
import shutil
import tempfile
import urllib.request
from pathlib import Path

REPO = "visolex/visobert-hsd"
BASE = "uitnlp/visobert"  # architecture config of the encoder
LABELS = ["CLEAN", "OFFENSIVE", "HATE"]


def fetch(repo: str, name: str, target: Path) -> Path:
    path = target / name
    urllib.request.urlretrieve(f"https://huggingface.co/{repo}/resolve/main/{name}", path)
    return path


def main() -> None:
    import numpy as np
    import onnxruntime as ort
    import torch
    from onnxruntime.quantization import QuantType, quantize_dynamic
    from safetensors.torch import load_file
    from transformers import XLMRobertaConfig, XLMRobertaModel

    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[1] / "models" / "visobert-hsd"))
    out = Path(ap.parse_args().out)
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        config = json.loads(fetch(BASE, "config.json", tmp).read_text())
        weights = load_file(str(fetch(REPO, "model.safetensors", tmp)))
        sp_path = fetch(REPO, "sentencepiece.bpe.model", tmp)

        class Classifier(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.encoder = XLMRobertaModel(XLMRobertaConfig.from_dict(config))
                self.classifier = torch.nn.Linear(config["hidden_size"], len(LABELS))

            def forward(self, input_ids, attention_mask):
                return self.classifier(self.encoder(input_ids=input_ids, attention_mask=attention_mask).pooler_output)

        model = Classifier()
        model.load_state_dict(weights, strict=True)
        model.eval()
        ids = torch.tensor([[0, 10, 11, 2], [0, 12, 2, 1]])
        mask = torch.tensor([[1, 1, 1, 1], [1, 1, 1, 0]])
        fp32 = tmp / "model.fp32.onnx"
        torch.onnx.export(model, (ids, mask), str(fp32), input_names=["input_ids", "attention_mask"], output_names=["logits"],
                          dynamic_axes={"input_ids": {0: "b", 1: "s"}, "attention_mask": {0: "b", 1: "s"}, "logits": {0: "b"}},
                          opset_version=17, dynamo=False)
        quantize_dynamic(str(fp32), str(out / "model.int8.onnx"), weight_type=QuantType.QInt8)
        shutil.copy(sp_path, out / "sentencepiece.bpe.model")
        # the quantised file must agree with the original network
        with torch.no_grad():
            want = torch.softmax(model(ids, mask), -1).numpy()
        session = ort.InferenceSession(str(out / "model.int8.onnx"), providers=["CPUExecutionProvider"])
        got = session.run(None, {"input_ids": ids.numpy(), "attention_mask": mask.numpy()})[0]
        got = np.exp(got) / np.exp(got).sum(-1, keepdims=True)
        print("largest probability difference after int8:", float(np.abs(got - want).max()))
    print("written to", out)


if __name__ == "__main__":
    main()
