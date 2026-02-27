"""
SAMS — Train All ML Models
Entry point for Docker ml_trainer service and CI pipeline.
"""
from ml_engine.dataset_generator import generate_dataset
from ml_engine.train_rf import train as train_rf
from ml_engine.train_torch import train as train_torch


def main() -> None:
    print("=" * 60)
    print("SAMS ML Training Pipeline")
    print("=" * 60)

    print("\n[1/3] Generating synthetic dataset …")
    generate_dataset(n_samples=5000)

    print("\n[2/3] Training RandomForest model …")
    rf_metrics = train_rf(n_samples=5000)
    print(f"      RF Accuracy: {rf_metrics['accuracy']:.3f}  F1: {rf_metrics['f1']:.3f}")

    print("\n[3/3] Training PyTorch MLP …")
    torch_metrics = train_torch(n_samples=5000, epochs=40)
    print(f"      Torch Accuracy: {torch_metrics['accuracy']:.3f}")

    print("\n✓ Training complete. Models saved to ml_engine/models/")
    print("=" * 60)


if __name__ == "__main__":
    main()
