"""
ACE Evaluator for Project Aether
Evaluates model responses against ground truth
"""

from typing import Dict, List, Optional, Tuple

from utils.logger import get_logger


class ACEEvaluator:
    """
    Evaluator for assessing model response quality.
    
    Provides metrics for accuracy and response quality.
    """
    
    def __init__(self):
        """Initialize the evaluator."""
        self.logger = get_logger("aether.evaluator")
    
    def answer_is_correct(
        self,
        predicted: str,
        expected: str,
        tolerance: float = 0.1
    ) -> Tuple[bool, float]:
        """
        Check if an answer is correct.
        
        For numeric answers, allows some tolerance.
        For text, does exact match (case-insensitive).
        
        Args:
            predicted: Model's predicted answer
            expected: Expected ground truth
            tolerance: Tolerance for numeric comparisons
            
        Returns:
            Tuple of (is_correct, confidence_score)
        """
        predicted = predicted.strip().lower()
        expected = expected.strip().lower()
        
        # Exact match
        if predicted == expected:
            return True, 1.0
        
        # Try numeric comparison
        try:
            pred_num = float(predicted)
            exp_num = float(expected)
            
            if abs(pred_num - exp_num) <= tolerance:
                return True, 1.0 - (abs(pred_num - exp_num) / (abs(exp_num) + 0.001))
        except ValueError:
            pass
        
        # Partial match for longer texts
        if len(expected) > 10:
            # Check if key words match
            expected_words = set(expected.split())
            predicted_words = set(predicted.split())
            overlap = len(expected_words & predicted_words) / len(expected_words)
            
            if overlap > 0.8:
                return True, overlap
        
        return False, 0.0
    
    def evaluate_accuracy(
        self,
        predictions: List[str],
        ground_truth: List[str]
    ) -> Dict:
        """
        Evaluate overall accuracy.
        
        Args:
            predictions: List of predicted answers
            ground_truth: List of expected answers
            
        Returns:
            Dictionary with accuracy metrics
        """
        if len(predictions) != len(ground_truth):
            raise ValueError("Predictions and ground truth must have same length")
        
        total = len(predictions)
        correct = 0
        total_confidence = 0.0
        
        for pred, truth in zip(predictions, ground_truth):
            is_correct, confidence = self.answer_is_correct(pred, truth)
            if is_correct:
                correct += 1
            total_confidence += confidence
        
        accuracy = correct / total if total > 0 else 0.0
        avg_confidence = total_confidence / total if total > 0 else 0.0
        
        return {
            "total_samples": total,
            "correct": correct,
            "incorrect": total - correct,
            "accuracy": accuracy,
            "average_confidence": avg_confidence
        }
    
    def evaluate_response_quality(
        self,
        response: str,
        criteria: Optional[List[str]] = None
    ) -> Dict:
        """
        Evaluate response quality based on criteria.
        
        Args:
            response: Response to evaluate
            criteria: List of quality criteria
            
        Returns:
            Quality metrics dictionary
        """
        if criteria is None:
            criteria = ["clarity", "completeness", "relevance"]
        
        # Basic metrics
        word_count = len(response.split())
        char_count = len(response)
        sentence_count = response.count('.') + response.count('!') + response.count('?')
        
        return {
            "word_count": word_count,
            "char_count": char_count,
            "sentence_count": max(1, sentence_count),
            "avg_words_per_sentence": word_count / max(1, sentence_count),
            "criteria_evaluated": criteria
        }


# Global evaluator instance
evaluator = ACEEvaluator()


def get_evaluator() -> ACEEvaluator:
    """Get the global evaluator instance."""
    return evaluator
