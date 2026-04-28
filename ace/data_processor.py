"""
ACE Data Processor for Project Aether
Processes and prepares data for evaluation
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from utils.logger import get_logger


class DataProcessor:
    """
    Processes task data for ACE evaluation.
    
    Handles loading, cleaning, and preparing datasets.
    """
    
    def __init__(self):
        """Initialize the data processor."""
        self.logger = get_logger("aether.data_processor")
        self.datasets_dir = Path(__file__).parent / "datasets"
    
    def process_task_data(self, raw_data: List[Dict]) -> List[Dict]:
        """
        Process raw task data into a standardized format.
        
        Args:
            raw_data: Raw data items
            
        Returns:
            Processed data items
        """
        processed = []
        
        for item in raw_data:
            if not isinstance(item, dict):
                continue
            
            # Standardize format
            processed_item = {
                "input": item.get("input", item.get("question", "")),
                "output": item.get("output", item.get("answer", "")),
                "metadata": item.get("metadata", {})
            }
            
            # Validate
            if processed_item["input"] and processed_item["output"]:
                processed.append(processed_item)
            else:
                self.logger.warning(f"Skipping invalid item: {item}")
        
        self.logger.info(f"Processed {len(processed)} valid items")
        return processed
    
    def load_and_process(self, dataset_name: str) -> List[Dict]:
        """
        Load a dataset and process it.
        
        Args:
            dataset_name: Name of dataset file (without .json)
            
        Returns:
            Processed data items
        """
        dataset_path = self.datasets_dir / f"{dataset_name}.json"
        
        if not dataset_path.exists():
            self.logger.warning(f"Dataset not found: {dataset_path}")
            return []
        
        try:
            with open(dataset_path, 'r') as f:
                raw_data = json.load(f)
            
            return self.process_task_data(raw_data)
            
        except json.JSONDecodeError as e:
            self.logger.error(f"Error loading dataset: {e}")
            return []
    
    def split_data(
        self,
        data: List[Dict],
        train_ratio: float = 0.7,
        val_ratio: float = 0.15
    ) -> Tuple[List[Dict], List[Dict], List[Dict]]:
        """
        Split data into train/val/test sets.
        
        Args:
            data: Full dataset
            train_ratio: Ratio for training set
            val_ratio: Ratio for validation set
            
        Returns:
            Tuple of (train, val, test) datasets
        """
        import random
        
        random.shuffle(data)
        
        n = len(data)
        train_end = int(n * train_ratio)
        val_end = int(n * (train_ratio + val_ratio))
        
        train = data[:train_end]
        val = data[train_end:val_end]
        test = data[val_end:]
        
        self.logger.info(
            f"Split data: train={len(train)}, val={len(val)}, test={len(test)}"
        )
        
        return train, val, test
    
    def save_dataset(self, data: List[Dict], filename: str):
        """
        Save dataset to file.
        
        Args:
            data: Data to save
            filename: Output filename
        """
        output_path = self.datasets_dir / filename
        
        with open(output_path, 'w') as f:
            json.dump(data, f, indent=2)
        
        self.logger.info(f"Saved {len(data)} items to {output_path}")


# Global data processor instance
data_processor = DataProcessor()


def get_data_processor() -> DataProcessor:
    """Get the global data processor instance."""
    return data_processor


def process_task_data(raw_data: List[Dict]) -> List[Dict]:
    """Convenience function to process task data."""
    return data_processor.process_task_data(raw_data)


def answer_is_correct(predicted: str, expected: str) -> bool:
    """
    Simple correctness check.
    
    Args:
        predicted: Predicted answer
        expected: Expected answer
        
    Returns:
        True if correct
    """
    return predicted.strip().lower() == expected.strip().lower()


def evaluate_accuracy(predictions: List[str], ground_truth: List[str]) -> float:
    """
    Calculate accuracy score.
    
    Args:
        predictions: List of predictions
        ground_truth: List of correct answers
        
    Returns:
        Accuracy as a float (0.0 to 1.0)
    """
    if len(predictions) != len(ground_truth):
        raise ValueError("Lists must have same length")
    
    correct = sum(
        1 for pred, truth in zip(predictions, ground_truth)
        if pred.strip().lower() == truth.strip().lower()
    )
    
    return correct / len(predictions) if predictions else 0.0
