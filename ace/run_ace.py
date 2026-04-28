#!/usr/bin/env python3
"""
ACE Runner for Project Aether
Runs ACE optimization and evaluation pipeline
"""

import json
from pathlib import Path

from ace.optimizer import get_optimizer
from ace.data_processor import get_data_processor
from ace.evaluator import get_evaluator
from utils.logger import get_logger


def run_ace_pipeline():
    """
    Run the complete ACE pipeline.
    
    1. Load datasets
    2. Process data
    3. Simulate optimization
    4. Output results
    """
    logger = get_logger("aether.run_ace")
    logger.info("=" * 50)
    logger.info("Starting ACE Pipeline")
    logger.info("=" * 50)
    
    # Initialize components
    optimizer = get_optimizer()
    data_processor = get_data_processor()
    evaluator = get_evaluator()
    
    # Step 1: Load datasets
    logger.info("\n[Step 1] Loading datasets...")
    
    train_data = data_processor.load_and_process("train")
    val_data = data_processor.load_and_process("val")
    test_data = data_processor.load_and_process("test")
    
    logger.info(f"  Train: {len(train_data)} items")
    logger.info(f"  Val: {len(val_data)} items")
    logger.info(f"  Test: {len(test_data)} items")
    
    if not train_data:
        logger.warning("No training data found. Creating sample data...")
        _create_sample_datasets()
        train_data = data_processor.load_and_process("train")
    
    # Step 2: Load current prompt
    logger.info("\n[Step 2] Loading current prompt...")
    
    prompts_dir = Path(__file__).parent.parent / "prompts"
    base_prompt_path = prompts_dir / "base_prompt.txt"
    
    if base_prompt_path.exists():
        current_prompt = base_prompt_path.read_text()
        logger.info(f"  Loaded prompt from {base_prompt_path}")
    else:
        current_prompt = "You are a helpful AI assistant."
        logger.info("  Using default prompt")
    
    # Step 3: Simulate optimization
    logger.info("\n[Step 3] Running optimization simulation...")
    
    optimized_prompt = optimizer.simulate_optimization(
        current_prompt=current_prompt,
        train_data=train_data,
        iterations=3
    )
    
    logger.info(f"  Original prompt length: {len(current_prompt)} chars")
    logger.info(f"  Optimized prompt length: {len(optimized_prompt)} chars")
    
    # Step 4: Save optimized prompt
    logger.info("\n[Step 4] Saving optimized prompt...")
    
    output_path = prompts_dir / "optimized_prompt.txt"
    optimizer.save_optimized_prompt(optimized_prompt, str(output_path))
    logger.info(f"  Saved to {output_path}")
    
    # Step 5: Evaluate (simulated)
    logger.info("\n[Step 5] Running evaluation...")
    
    # Simulate predictions vs ground truth
    sample_predictions = ["4", "Paris", "42"]
    sample_ground_truth = ["4", "Paris", "42"]
    
    accuracy_result = evaluator.evaluate_accuracy(
        predictions=sample_predictions,
        ground_truth=sample_ground_truth
    )
    
    logger.info(f"  Sample accuracy: {accuracy_result['accuracy']:.2%}")
    logger.info(f"  Correct: {accuracy_result['correct']}/{accuracy_result['total_samples']}")
    
    # Summary
    logger.info("\n" + "=" * 50)
    logger.info("ACE Pipeline Complete!")
    logger.info("=" * 50)
    logger.info(f"\nOptimized prompt saved to: {output_path}")
    logger.info("\nTo use the optimized prompt:")
    logger.info("  1. Review the optimized_prompt.txt file")
    logger.info("  2. Run: python main.py")
    logger.info("  3. The agent will automatically use the optimized prompt")
    
    return {
        "success": True,
        "optimized_prompt_path": str(output_path),
        "train_items": len(train_data),
        "val_items": len(val_data),
        "test_items": len(test_data),
        "sample_accuracy": accuracy_result['accuracy']
    }


def _create_sample_datasets():
    """Create sample datasets if they don't exist."""
    datasets_dir = Path(__file__).parent / "datasets"
    datasets_dir.mkdir(exist_ok=True)
    
    train_data = [
        {"input": "What is 2+2?", "output": "4"},
        {"input": "What is the capital of France?", "output": "Paris"},
        {"input": "What is 6*7?", "output": "42"},
        {"input": "Who wrote Romeo and Juliet?", "output": "Shakespeare"},
        {"input": "What is H2O?", "output": "Water"}
    ]
    
    val_data = [
        {"input": "What is 10/2?", "output": "5"},
        {"input": "What color is the sky?", "output": "Blue"}
    ]
    
    test_data = [
        {"input": "What is 3+3?", "output": "6"},
        {"input": "What planet is known as the Red Planet?", "output": "Mars"}
    ]
    
    with open(datasets_dir / "train.json", 'w') as f:
        json.dump(train_data, f, indent=2)
    
    with open(datasets_dir / "val.json", 'w') as f:
        json.dump(val_data, f, indent=2)
    
    with open(datasets_dir / "test.json", 'w') as f:
        json.dump(test_data, f, indent=2)


if __name__ == "__main__":
    result = run_ace_pipeline()
    
    if result["success"]:
        print("\n✅ ACE pipeline completed successfully!")
    else:
        print("\n❌ ACE pipeline encountered issues.")
