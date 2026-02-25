"""Example customer training loop (edit this file for custom logic)."""

from __future__ import annotations

import asyncio
import os
from typing import Any, Dict, Callable

import torch

from runtime import JobReporter


def build_model() -> torch.nn.Module:
    """Construct a simple MLP for the synthetic training run."""
    return torch.nn.Sequential(
        torch.nn.Linear(128, 64),
        torch.nn.ReLU(),
        torch.nn.Linear(64, 10),
    )


def build_data(batch_size: int, val_split: float = 0.2, seed: int = 42):
    """Create synthetic training/validation data loaders."""
    import torch.utils.data as data

    gen = torch.Generator().manual_seed(seed)
    X = torch.randn(2000, 128, generator=gen)
    weights = torch.randn(10, 128, generator=gen)
    logits = X @ weights.T
    y = logits.argmax(dim=1)
    dataset = data.TensorDataset(X, y)
    val_size = int(len(dataset) * val_split)
    train_size = len(dataset) - val_size
    train_ds, val_ds = data.random_split(dataset, [train_size, val_size], generator=gen)
    train_loader = data.DataLoader(train_ds, batch_size=batch_size, shuffle=True)
    val_loader = data.DataLoader(val_ds, batch_size=batch_size, shuffle=False)
    return train_loader, val_loader


async def run_training(
    cfg: Dict[str, Any],
    reporter: JobReporter,
    should_terminate: Callable[[], bool],
) -> int:
    """Run training and report logs/metrics via the reporter."""
    job_id = str(cfg.get("job_id", "unknown"))
    await reporter.log("INFO", "Building synthetic dataset")
    val_split = float(cfg.get("val_split", 0.2))
    loader, val_loader = build_data(
        cfg.get("batch_size", 32),
        val_split=val_split,
        seed=int(cfg.get("seed", 42)),
    )
    model = build_model()
    opt = torch.optim.Adam(model.parameters(), lr=cfg.get("lr", 1e-3))
    epochs = int(cfg.get("epochs", 1))
    fail_after_epoch = cfg.get("fail_after_epoch")

    await reporter.log("INFO", "Training started")
    for e in range(epochs):
        if should_terminate():
            await reporter.log("WARNING", "Cancellation requested")
            await reporter.cancelled(epoch=e)
            return 0

        # Guaranteed failure for testing purposes
        if fail_after_epoch and (e + 1) >= int(fail_after_epoch):
            raise RuntimeError(f"forced failure at epoch {e + 1}")

        total = 0.0
        for X, y in loader:
            out = model(X)
            loss = torch.nn.functional.cross_entropy(out, y)
            opt.zero_grad()
            loss.backward()
            opt.step()
            total += loss.item()

        avg = total / len(loader)
        model.eval()
        correct = 0
        seen = 0
        with torch.no_grad():
            for X, y in val_loader:
                out = model(X)
                preds = out.argmax(dim=1)
                correct += (preds == y).sum().item()
                seen += y.numel()
        model.train()

        accuracy = (correct / seen) if seen else 0.0
        await reporter.epoch_metric(e + 1, {"loss": avg, "accuracy": accuracy})
        await reporter.log(
            "INFO",
            f"Epoch {e+1}/{epochs} completed, loss={avg:.4f}, acc={accuracy:.4f}",
        )
        await asyncio.sleep(0.1)

    await reporter.log("INFO", "Training completed successfully")
    artifact_uri = (
        cfg.get("artifact_uri")
        or os.getenv("ARTIFACT_URI")
        or f"s3://example-bucket/ai-trainops/artifacts/{job_id}/"
    )
    if not cfg.get("artifact_uri") and not os.getenv("ARTIFACT_URI"):
        await reporter.log(
            "INFO",
            f"Emitting example artifact URI for demo: {artifact_uri}",
        )
    await reporter.artifacts_ready(
        artifact_uri=str(artifact_uri),
        dataset_uri=cfg.get("dataset_uri"),
    )
    return 0
